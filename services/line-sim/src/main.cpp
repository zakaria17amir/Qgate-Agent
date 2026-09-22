// line-sim: replay a manifest onto Redpanda at takt (ADR-011).
//
// The pure parts (schedule, manifest, wire framing) live in the headers and have Catch2 tests.
// This file is the edge producer's plumbing: registry lookup, librdkafka, delivery counters,
// a /metrics endpoint and a clean stop on SIGTERM.

#include <httplib.h>
#include <librdkafka/rdkafka.h>

#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <map>
#include <mutex>
#include <nlohmann/json.hpp>
#include <sstream>
#include <string>
#include <thread>

#include "manifest.hpp"
#include "scheduler.hpp"
#include "wire.hpp"

namespace {

struct Args {
    std::string file;
    std::string brokers = "redpanda:9092";
    std::string registry = "http://redpanda:8081";
    std::string schemas = "/schemas";
    double speed = 10.0;
    int metrics_port = 8010;
};

Args parse(int argc, char** argv) {
    Args a;
    for (int i = 1; i + 1 < argc; i += 2) {
        const std::string k = argv[i], v = argv[i + 1];
        if (k == "--file")
            a.file = v;
        else if (k == "--brokers")
            a.brokers = v;
        else if (k == "--registry")
            a.registry = v;
        else if (k == "--schemas")
            a.schemas = v;
        else if (k == "--speed")
            a.speed = std::stod(v);
        else if (k == "--metrics-port")
            a.metrics_port = std::stoi(v);
        else
            throw std::invalid_argument("unknown argument " + k);
    }
    if (a.file.empty()) throw std::invalid_argument("--file is required");
    return a;
}

// Delivery counters, read by /metrics from another thread.
struct Counters {
    std::mutex m;
    std::map<std::string, std::uint64_t> delivered;
    std::atomic<std::uint64_t> errors{0};
    std::atomic<std::uint64_t> scheduled{0};

    std::string prometheus() {
        std::ostringstream out;
        out << "# TYPE line_sim_events_total counter\n";
        {
            std::lock_guard<std::mutex> lock(m);
            for (const auto& [topic, n] : delivered)
                out << "line_sim_events_total{topic=\"" << topic << "\"} " << n << "\n";
        }
        out << "# TYPE line_sim_scheduled_total counter\nline_sim_scheduled_total " << scheduled
            << "\n# TYPE line_sim_errors_total counter\nline_sim_errors_total " << errors << "\n";
        return out.str();
    }
};

std::atomic<bool> g_stop{false};
void on_signal(int) {
    g_stop = true;
}

// Register (idempotently) the topic's schema under TopicNameStrategy and return its id. The
// registry canonicalises, so this is the same id the Python serialiser gets.
std::uint32_t schema_id(httplib::Client& registry, const std::string& schemas_dir,
                        const std::string& topic) {
    std::ifstream f(schemas_dir + "/" + topic + ".v1.avsc");
    if (!f) throw std::runtime_error("no schema file for " + topic);
    std::stringstream avsc;
    avsc << f.rdbuf();
    const nlohmann::json body = {{"schema", avsc.str()}};
    auto res = registry.Post("/subjects/" + topic + "-value/versions", body.dump(),
                             "application/vnd.schemaregistry.v1+json");
    if (!res || res->status >= 300)
        throw std::runtime_error("schema registry refused " + topic + ": " +
                                 (res ? std::to_string(res->status) + " " + res->body
                                      : httplib::to_string(res.error())));
    return nlohmann::json::parse(res->body).at("id").get<std::uint32_t>();
}

void on_delivery(rd_kafka_t*, const rd_kafka_message_t* msg, void* opaque) {
    auto* c = static_cast<Counters*>(opaque);
    if (msg->err) {
        c->errors++;
        std::fprintf(stderr, "delivery failed: %s\n", rd_kafka_err2str(msg->err));
        return;
    }
    std::lock_guard<std::mutex> lock(c->m);
    c->delivered[rd_kafka_topic_name(msg->rkt)]++;
}

rd_kafka_t* make_producer(const std::string& brokers, Counters& counters) {
    char err[512];
    rd_kafka_conf_t* conf = rd_kafka_conf_new();
    for (const auto& [k, v] : std::map<std::string, std::string>{
             {"bootstrap.servers", brokers},
             {"enable.idempotence", "true"},  // same guarantees as the Python producer
             {"linger.ms", "20"},
             {"compression.type", "lz4"},
         })
        if (rd_kafka_conf_set(conf, k.c_str(), v.c_str(), err, sizeof err) != RD_KAFKA_CONF_OK)
            throw std::runtime_error(err);
    rd_kafka_conf_set_dr_msg_cb(conf, on_delivery);
    rd_kafka_conf_set_opaque(conf, &counters);
    rd_kafka_t* rk = rd_kafka_new(RD_KAFKA_PRODUCER, conf, err, sizeof err);
    if (!rk) throw std::runtime_error(err);
    return rk;
}

}  // namespace

int main(int argc, char** argv) try {
    const Args args = parse(argc, argv);
    std::signal(SIGTERM, on_signal);
    std::signal(SIGINT, on_signal);

    std::ifstream in(args.file);
    if (!in) throw std::runtime_error("cannot open " + args.file);
    const auto events = line_sim::read_manifest(in);
    if (events.empty()) {
        std::printf("line-sim %s: empty manifest, nothing to do\n", line_sim::kVersion);
        return 0;
    }

    httplib::Client registry(args.registry);
    std::map<std::string, std::uint32_t> ids;
    for (const auto& e : events)
        if (!ids.count(e.topic)) ids[e.topic] = schema_id(registry, args.schemas, e.topic);

    Counters counters;
    httplib::Server metrics;
    metrics.Get("/metrics", [&](const httplib::Request&, httplib::Response& res) {
        res.set_content(counters.prometheus(), "text/plain; version=0.0.4");
    });
    metrics.Get("/health", [](const httplib::Request&, httplib::Response& res) {
        res.set_content("{\"status\":\"ok\",\"service\":\"line-sim\"}", "application/json");
    });
    std::thread metrics_thread([&] { metrics.listen("0.0.0.0", args.metrics_port); });

    rd_kafka_t* rk = make_producer(args.brokers, counters);
    std::printf("line-sim %s: %zu events from %s at %gx to %s\n", line_sim::kVersion, events.size(),
                args.file.c_str(), args.speed, args.brokers.c_str());

    const auto start = std::chrono::steady_clock::now();
    const auto first_ts = events.front().ts_ms;
    for (const auto& e : events) {
        const auto due = line_sim::due_at(start, first_ts, e.ts_ms, args.speed);
        while (!g_stop &&
               std::chrono::steady_clock::now() < due) {  // short naps: stop stays responsive
            rd_kafka_poll(rk, 0);
            std::this_thread::sleep_for(std::min(due - std::chrono::steady_clock::now(),
                                                 std::chrono::nanoseconds(100'000'000)));
        }
        if (g_stop) break;
        const std::string value = line_sim::frame(ids[e.topic], e.value);
        for (;;) {
            const auto err = rd_kafka_producev(
                rk, RD_KAFKA_V_TOPIC(e.topic.c_str()), RD_KAFKA_V_KEY(e.key.data(), e.key.size()),
                RD_KAFKA_V_VALUE(const_cast<char*>(value.data()), value.size()),
                RD_KAFKA_V_MSGFLAGS(RD_KAFKA_MSG_F_COPY), RD_KAFKA_V_TIMESTAMP(e.ts_ms),
                RD_KAFKA_V_END);
            if (err == RD_KAFKA_RESP_ERR_NO_ERROR) break;
            if (err != RD_KAFKA_RESP_ERR__QUEUE_FULL)
                throw std::runtime_error(rd_kafka_err2str(err));
            rd_kafka_poll(rk, 100);  // backpressure: let deliveries drain, then retry this event
        }
        counters.scheduled++;
        rd_kafka_poll(rk, 0);
    }

    // Stop or end of stream: every enqueued message is acknowledged before we exit.
    const auto pending = rd_kafka_flush(rk, 30'000);
    rd_kafka_destroy(rk);
    metrics.stop();
    metrics_thread.join();

    std::uint64_t delivered = 0;
    for (const auto& [_, n] : counters.delivered) delivered += n;
    std::printf("line-sim: scheduled %llu, delivered %llu, errors %llu%s\n",
                static_cast<unsigned long long>(counters.scheduled),
                static_cast<unsigned long long>(delivered),
                static_cast<unsigned long long>(counters.errors),
                g_stop ? " (stopped by signal)" : "");
    return (counters.errors == 0 && pending == RD_KAFKA_RESP_ERR_NO_ERROR) ? 0 : 1;
} catch (const std::exception& e) {
    std::fprintf(stderr, "line-sim: %s\n", e.what());
    return 2;
}
