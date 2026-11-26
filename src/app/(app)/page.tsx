import { ComingSoon, PageHeader } from "@/components/page-placeholder";

export default function HomePage() {
  return (
    <>
      <PageHeader title="오늘 구해야 할 재료" description="유통기한이 임박한 재료와 추천 레시피를 보여줘요." />
      <ComingSoon
        phase="Phase 1·3"
        items={["임박 재료 배너 (D-3 이하)", "구출 레시피 추천 카드 3개", "에이전트에게 바로 물어보는 입력창"]}
      />
    </>
  );
}
