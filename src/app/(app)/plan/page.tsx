import { ComingSoon, PageHeader } from "@/components/page-placeholder";

export default function PlanPage() {
  return (
    <>
      <PageHeader title="이번 주 식단" description="일정에 맞춘 식단과 장보기 목록이에요." />
      <ComingSoon
        phase="Phase 5"
        items={["7일 식단 자동 생성 (바쁜 날 10분 요리, 운동 날 고단백)", "부족한 재료만 모은 장보기 목록", "구매 완료 → 재고로 바로 등록"]}
      />
    </>
  );
}
