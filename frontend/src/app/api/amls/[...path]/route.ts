import { proxyRequest } from "@/lib/api-proxy";


async function proxyAmlsRequest(
  request: Request,
  params: Promise<{ path: string[] }>,
): Promise<Response> {
  const { path } = await params;
  const backendPath = `/${path.join("/")}`;
  return proxyRequest(request, backendPath);
}


export async function GET(
  request: Request,
  { params }: { params: Promise<{ path: string[] }> },
) {
  return proxyAmlsRequest(request, params);
}


export async function POST(
  request: Request,
  { params }: { params: Promise<{ path: string[] }> },
) {
  return proxyAmlsRequest(request, params);
}


export async function PATCH(
  request: Request,
  { params }: { params: Promise<{ path: string[] }> },
) {
  return proxyAmlsRequest(request, params);
}


export async function PUT(
  request: Request,
  { params }: { params: Promise<{ path: string[] }> },
) {
  return proxyAmlsRequest(request, params);
}


export async function DELETE(
  request: Request,
  { params }: { params: Promise<{ path: string[] }> },
) {
  return proxyAmlsRequest(request, params);
}
