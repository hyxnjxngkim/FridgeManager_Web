# FridgeManager_Web
냉장고를 부탁해 — 유통기한 임박 재료부터 쓰는 레시피를 추천하는 냉장고 에이전트.
기획은 [PLAN.md](PLAN.md)를 보세요.

## 스택
Next.js 15 (App Router) · TypeScript · Tailwind CSS v4 · shadcn/ui · Supabase (Postgres + pgvector + Auth) · Claude API
배포는 마지막에 AWS로 합니다 (`output: "standalone"` 빌드, `/healthz` 헬스체크 준비됨).

## 처음 실행하기
1. Node.js 20 이상(LTS)을 설치해요 — https://nodejs.org
2. 의존성 설치
   ```bash
   npm install
   ```
3. Supabase 프로젝트를 만들고 SQL Editor에서 `supabase/migrations/0001_init.sql`을 실행해요.
4. 환경변수 파일을 만들고 값을 채워요 (Supabase > Settings > API).
   ```bash
   cp .env.local.example .env.local
   ```
5. 개발 서버 실행 → http://localhost:3000
   ```bash
   npm run dev
   ```

## 폴더 구조
```
src/
  app/
    (auth)/login/      로그인·회원가입
    (app)/             로그인 후 화면 (홈, 재고, 달력, 채팅, 식단, 통계, 설정)
    auth/confirm       가입 확인 메일 콜백
    auth/signout       로그아웃
    healthz            헬스체크
  components/ui/       shadcn/ui 컴포넌트
  lib/supabase/        Supabase 클라이언트 (브라우저/서버/미들웨어)
supabase/migrations/   DB 스키마 + RLS
```

shadcn/ui 컴포넌트 추가: `npx shadcn@latest add table dialog ...`
