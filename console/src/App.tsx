import { NavLink, Outlet } from "react-router-dom";
import { TokenDrawer } from "./auth/TokenDrawer";

/** One layout for the four routes: a rail with the two lists and the token, then the page. */
export function App() {
  return (
    <div className="shell">
      <aside className="rail">
        <div className="brand">
          qgate
          <small>end-of-line containment</small>
        </div>
        <nav aria-label="Pages">
          <NavLink to="/queue">Queue</NavLink>
          <NavLink to="/audit">Audit</NavLink>
        </nav>
        <div className="spacer" />
        <TokenDrawer />
      </aside>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
