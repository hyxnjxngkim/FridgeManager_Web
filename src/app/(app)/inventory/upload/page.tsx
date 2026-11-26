import { ComingSoon, PageHeader } from "@/components/page-placeholder";

export default function UploadPage() {
  return (
    <>
      <PageHeader title="재료 등록" description="영수증이나 냉장고 사진을 올리면 재료를 뽑아줘요." />
      <ComingSoon
        phase="Phase 2"
        items={["영수증 인식 (Claude Haiku)", "냉장고 사진 인식 (Claude Sonnet)", "인식 결과 확인·수정 후 저장"]}
      />
    </>
  );
}
