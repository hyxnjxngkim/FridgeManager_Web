import { ComingSoon, PageHeader } from "@/components/page-placeholder";

export default function ChatPage() {
  return (
    <>
      <PageHeader title="냉장고 에이전트" description="무엇을 만들지 물어보세요." />
      <ComingSoon
        phase="Phase 4"
        items={["임박 재료 우선 레시피 추천 (출처 포함)", "\"이거 만들게\" → 재고 자동 차감", "취향·알레르기 기억"]}
      />
    </>
  );
}
