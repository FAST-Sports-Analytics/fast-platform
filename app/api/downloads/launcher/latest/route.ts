import { NextRequest, NextResponse } from "next/server";

function cloudBase() {
  return (process.env.FAST_CLOUD_URL || process.env.NEXT_PUBLIC_FAST_CLOUD_URL || "").replace(/\/+$/, "");
}

export async function GET(request: NextRequest) {
  const base = cloudBase();
  const authorization = request.headers.get("authorization") || "";
  if (!base) return NextResponse.json({ detail: "FAST Cloud is not configured." }, { status: 503 });
  if (!authorization) return NextResponse.json({ detail: "Sign in to FAST first." }, { status: 401 });
  try {
    const response = await fetch(`${base}/api/v1/customer-downloads/launcher/latest`, {
      headers: { Accept: "application/json", Authorization: authorization },
      cache: "no-store",
    });
    const body = await response.text();
    return new NextResponse(body, {
      status: response.status,
      headers: { "Content-Type": response.headers.get("content-type") || "application/json" },
    });
  } catch {
    return NextResponse.json({ detail: "FAST could not reach FAST Cloud." }, { status: 502 });
  }
}
