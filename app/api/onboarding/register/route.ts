import { NextRequest, NextResponse } from "next/server";

function cloudBase() {
  return (process.env.FAST_CLOUD_URL || process.env.NEXT_PUBLIC_FAST_CLOUD_URL || "").replace(/\/+$/, "");
}

export async function POST(request: NextRequest) {
  const base = cloudBase();
  if (!base) {
    return NextResponse.json(
      { detail: "FAST Cloud is not configured for this website deployment." },
      { status: 503 },
    );
  }

  try {
    const body = await request.text();
    const response = await fetch(`${base}/api/v1/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body,
      cache: "no-store",
    });
    const text = await response.text();
    return new NextResponse(text, {
      status: response.status,
      headers: { "Content-Type": response.headers.get("content-type") || "application/json" },
    });
  } catch {
    return NextResponse.json(
      { detail: "FAST could not reach FAST Cloud. Please try again shortly." },
      { status: 502 },
    );
  }
}
