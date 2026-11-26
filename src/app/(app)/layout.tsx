import Link from "next/link";
import { redirect } from "next/navigation";
import { LogOut, Refrigerator, Settings } from "lucide-react";
import { BottomNav, TopNav } from "@/components/app-nav";
import { SetupNotice } from "@/components/setup-notice";
import { Button } from "@/components/ui/button";
import { isSupabaseConfigured } from "@/lib/supabase/env";
import { createClient } from "@/lib/supabase/server";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  if (!isSupabaseConfigured()) return <SetupNotice />;

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  return (
    <div className="min-h-dvh pb-20 md:pb-0">
      <header className="sticky top-0 z-30 border-b bg-background/95 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-5xl items-center justify-between gap-4 px-4">
          <Link href="/" className="flex items-center gap-2 font-semibold">
            <Refrigerator className="size-5 text-primary" />
            냉장고를 부탁해
          </Link>
          <TopNav />
          <div className="flex items-center gap-1">
            <Button asChild variant="ghost" size="icon" aria-label="설정">
              <Link href="/settings">
                <Settings />
              </Link>
            </Button>
            <form action="/auth/signout" method="post">
              <Button type="submit" variant="ghost" size="icon" aria-label="로그아웃">
                <LogOut />
              </Button>
            </form>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-6">{children}</main>
      <BottomNav />
    </div>
  );
}
