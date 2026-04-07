import { RouteLoadingScreen } from "@/components/AppLoading";


export default function CourseLectureLoading() {
  return (
    <RouteLoadingScreen
      title="Loading lecture"
      message="Preparing lecture content..."
    />
  );
}
