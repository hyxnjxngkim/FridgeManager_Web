import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // AWS(ECS/App Runner/Lambda 컨테이너 등) 배포를 위해 독립 실행형 빌드 생성
  output: "standalone",
};

export default nextConfig;
