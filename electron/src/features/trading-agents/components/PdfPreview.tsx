/**
 * PDF 预览 — 浏览器原生 iframe 内联渲染（最可靠：清晰、可滚动、可翻页）
 * 外层浅色容器包裹，PDF 页面本身白色，整体浅色观感。
 */
import React from 'react';

interface PdfPreviewProps {
  url: string;
  filename: string;
}

const PdfPreview: React.FC<PdfPreviewProps> = ({ url }) => {
  return (
    <iframe
      src={url}
      style={{
        width: '100%',
        border: 'none',
        height: 'calc(88vh - 45px)',
        minHeight: 500,
        background: '#f8fafc',
      }}
      title="PDF 预览"
    />
  );
};

export default PdfPreview;
