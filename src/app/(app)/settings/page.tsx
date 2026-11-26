import { ComingSoon, PageHeader } from "@/components/page-placeholder";
import { createClient } from "@/lib/supabase/server";

export default async function SettingsPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  return (
    <>
      <PageHeader title="설정" description={user?.email ?? undefined} />
      <ComingSoon
        phase="Phase 4"
        items={["기억한 취향·알레르기 보기 / 삭제", "식단 목표 (다이어트, 고단백 등)"]}
      />
    </>
  );
}
