import { proxyRequest } from "@/lib/api-proxy";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ path?: string[] }> }
) {
  const { path: pathSegments } = await params;
  const path = pathSegments ? `/${pathSegments.join("/")}` : "";
  return proxyRequest(request, `/entrance-test${path}`);
}

export async function POST(
  request: Request,
  { params }: { params: Promise<{ path?: string[] }> }
) {
  const { path: pathSegments } = await params;
  const path = pathSegments ? `/${pathSegments.join("/")}` : "";
  return proxyRequest(request, `/entrance-test${path}`);
}
