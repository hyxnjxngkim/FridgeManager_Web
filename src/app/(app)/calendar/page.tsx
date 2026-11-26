import { ComingSoon, PageHeader } from "@/components/page-placeholder";

export default function CalendarPage() {
  return (
    <>
      <PageHeader title="달력" description="내 일정과 유통기한 임박 재료를 한눈에 봐요." />
      <ComingSoon
        phase="Phase 5"
        items={["일정 등록 (바쁜 날 / 운동 / 손님)", "날짜별 임박 재료 뱃지", "날짜를 누르면 그날 맞춤 추천"]}
      />
    </>
  );
}
