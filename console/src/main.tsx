import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import {
  createBrowserRouter,
  Navigate,
  RouterProvider,
} from "react-router-dom";
import { App } from "./App";
import { Audit } from "./pages/Audit";
import { Case } from "./pages/Case";
import { Decide } from "./pages/Decide";
import { Queue } from "./pages/Queue";
import "./tokens.css";

const client = new QueryClient({
  defaultOptions: { queries: { retry: false } },
});
// a new token makes every earlier answer stale, 401s included: refetch instead of waiting a poll
window.addEventListener("qgate-token", () => void client.invalidateQueries());

const router = createBrowserRouter([
  {
    path: "/",
    element: <App />,
    children: [
      { index: true, element: <Navigate to="/queue" replace /> },
      { path: "queue", element: <Queue /> },
      { path: "case/:id", element: <Case /> },
      { path: "case/:id/decide", element: <Decide /> },
      { path: "audit", element: <Audit /> },
    ],
  },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
