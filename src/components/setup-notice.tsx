export function SetupNotice() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-lg flex-col justify-center gap-4 px-4">
      <h1 className="text-2xl font-bold">Supabase 설정이 필요해요</h1>
      <ol className="list-decimal space-y-2 pl-5 text-sm text-muted-foreground">
        <li>supabase.com에서 프로젝트를 만들어요.</li>
        <li>
          <code>.env.local.example</code>을 <code>.env.local</code>로 복사하고 URL과 anon key를
          채워요.
        </li>
        <li>
          SQL Editor에서 <code>supabase/migrations/0001_init.sql</code>을 실행해요.
        </li>
        <li>
          개발 서버를 다시 시작해요 (<code>npm run dev</code>).
        </li>
      </ol>
    </main>
  );
}
