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
    const response = await fetch(`${base}/api/v1/customer-downloads/launcher/file`, {
      headers: { Authorization: authorization },
      cache: "no-store",
    });
    if (!response.ok) {
      const body = await response.text();
      return new NextResponse(body, {
        status: response.status,
        headers: { "Content-Type": response.headers.get("content-type") || "application/json" },
      });
    }
    return new NextResponse(response.body, {
      status: response.status,
      headers: {
        "Content-Type": response.headers.get("content-type") || "application/vnd.microsoft.portable-executable",
        "Content-Disposition": response.headers.get("content-disposition") || 'attachment; filename="FAST_Launcher_Setup.exe"',
        "Content-Length": response.headers.get("content-length") || "",
      },
    });
  } catch {
    return NextResponse.json({ detail: "FAST could not reach FAST Cloud." }, { status: 502 });
  }
}
