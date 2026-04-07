import { RouteLoadingScreen } from "@/components/AppLoading";


export default function CourseWorkspaceLoading() {
  return (
    <RouteLoadingScreen
      title="Loading workspace"
      message="Building your course workspace and graph..."
    />
  );
}
