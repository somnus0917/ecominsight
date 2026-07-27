import { AppShell } from "./layout/AppShell";
import { AnomalyDetailPage } from "./pages/AnomalyDetailPage";
import { AnomaliesPage } from "./pages/AnomaliesPage";
import { FinancePage } from "./pages/FinancePage";
import { InventoryPage } from "./pages/InventoryPage";
import { OverviewPage } from "./pages/OverviewPage";
import { ProductsPage } from "./pages/ProductsPage";
import { SearchPage } from "./pages/SearchPage";
import { ShopsPage } from "./pages/ShopsPage";
import { useRouter } from "./router";

export function App() {
  const { path } = useRouter();
  let page = <OverviewPage />;
  if (path === "/shops") page = <ShopsPage />;
  else if (path === "/products") page = <ProductsPage />;
  else if (path === "/search") page = <SearchPage />;
  else if (path === "/inventory") page = <InventoryPage />;
  else if (path === "/finance") page = <FinancePage />;
  else if (path === "/anomalies") page = <AnomaliesPage />;
  else if (path.startsWith("/anomalies/")) {
    page = <AnomalyDetailPage attributionId={path.split("/").filter(Boolean).at(-1) ?? ""} />;
  }
  return (
    <AppShell>{page}</AppShell>
  );
}
