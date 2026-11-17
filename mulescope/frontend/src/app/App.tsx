/**
 * Root: providers (TanStack Query, account drawer) and routes. The Evals page
 * and the case workspace (which carries React Flow) are lazy-loaded.
 */
import { lazy, Suspense } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createBrowserRouter, RouterProvider } from "react-router";
import { Layout } from "./Layout";
import { AccountDrawerProvider } from "./AccountDrawerContext";
import { QueuePage } from "../features/queue/QueuePage";
import { SkeletonRows } from "../components/ui/primitives";

const CaseWorkspace = lazy(() => import("../features/case-workspace/CaseWorkspace"));
const EvalsPage = lazy(() => import("../features/evals/EvalsPage"));

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 5_000, refetchOnWindowFocus: false, retry: 1 } },
});

const fallback = <SkeletonRows rows={8} />;

const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <QueuePage /> },
      { path: "cases/:caseId", element: <Suspense fallback={fallback}><CaseWorkspace /></Suspense> },
      { path: "evals", element: <Suspense fallback={fallback}><EvalsPage /></Suspense> },
    ],
  },
]);

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AccountDrawerProvider>
        <RouterProvider router={router} />
      </AccountDrawerProvider>
    </QueryClientProvider>
  );
}
