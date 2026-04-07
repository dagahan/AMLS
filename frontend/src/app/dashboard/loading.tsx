import { RouteLoadingScreen } from "@/components/AppLoading";


export default function DashboardLoading() {
  return (
    <RouteLoadingScreen
      title="Loading dashboard"
      message="Preparing your courses and enrollment data..."
    />
  );
}
