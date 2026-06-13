import { NextRequest } from "next/server";
import { proxyVoice } from "../../[...path]/route";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  return proxyVoice(req, ["session", "reply"]);
}
