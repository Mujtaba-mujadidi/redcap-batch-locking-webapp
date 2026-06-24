import { NextResponse } from "next/server";

export function createRedirectResponse(path: string) {
  return new NextResponse(null, {
    status: 303,
    headers: {
      location: path,
    },
  });
}
