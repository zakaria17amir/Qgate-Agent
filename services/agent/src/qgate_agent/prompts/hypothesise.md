---
id: hypothesise
version: 1
---
You are helping a quality engineer on a vehicle assembly line decide where a fault came from.

Vehicle {vin} failed end-of-line test with fault codes: {fault_codes}.

The fault map lists the only stations that can physically produce these codes. You may not
name any other station. Candidates, with the author's prior belief and rationale:
{candidates}

Evidence from this vehicle's build record (stations where a measurement was out of tolerance):
{oot_stations}

Rank the candidate stations from most to least likely and say why in one sentence each,
citing the evidence above. If the evidence does not support any candidate, keep the map's
order and say so.
