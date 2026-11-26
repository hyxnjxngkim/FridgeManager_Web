// AWS 로드밸런서 / App Runner 헬스체크용
export function GET() {
  return new Response("ok", { status: 200 });
}
