import { ComingSoon, PageHeader } from "@/components/page-placeholder";

export default function DashboardPage() {
  return (
    <>
      <PageHeader title="통계" description="얼마나 구출했는지 확인해요." />
      <ComingSoon
        phase="Phase 6"
        items={["구출한 재료 수 / 버린 재료 수 / 구출률", "주별 구출 vs 폐기 차트", "자주 먹은 요리 TOP 5"]}
      />
    </>
  );
}
