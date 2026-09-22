import { useEffect, useRef, useState } from "react";
import { claims, getToken, setToken } from "./token";

/** The rail's "Token" button and the dialog behind it. No auth UI beyond a paste (§6.6). */
export function TokenDrawer() {
  const ref = useRef<HTMLDialogElement>(null);
  const [value, setValue] = useState("");
  const [who, setWho] = useState(claims());

  useEffect(() => {
    const sync = () => setWho(claims());
    window.addEventListener("qgate-token", sync);
    return () => window.removeEventListener("qgate-token", sync);
  }, []);

  const open = () => {
    setValue(getToken() ?? "");
    ref.current?.showModal();
  };
  const use = () => {
    setToken(value || null);
    ref.current?.close();
  };

  return (
    <>
      <div className="muted" style={{ fontSize: "var(--fs-0)" }}>
        {who ? (
          <>
            <span className="mono">{who.sub}</span> · {who.role}
          </>
        ) : (
          "No token"
        )}
      </div>
      <button className="btn quiet" onClick={open}>
        Token
      </button>
      <dialog ref={ref}>
        <h2>Access token</h2>
        <p className="muted">
          Paste the JWT you were given. It stays in this browser tab and is sent
          only to the api.
        </p>
        <label className="field">
          <span>Access token</span>
          <input
            type="password"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            autoComplete="off"
            spellCheck={false}
          />
        </label>
        <div
          style={{
            display: "flex",
            gap: "var(--s-2)",
            justifyContent: "flex-end",
          }}
        >
          <button className="btn quiet" onClick={() => ref.current?.close()}>
            Cancel
          </button>
          <button className="btn" onClick={use}>
            Use token
          </button>
        </div>
      </dialog>
    </>
  );
}
