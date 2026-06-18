import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";
import "github-markdown-css/github-markdown-light.css";

interface MarkdownContentProps {
  content: string;
  className?: string;
}

/** Agent message markdown: react-markdown + GFM + GitHub default styles. */
export function MarkdownContent({ content, className = "" }: MarkdownContentProps) {
  if (!content.trim()) return null;

  return (
    <article className={`markdown-body min-w-0 max-w-full overflow-x-auto ${className}`.trim()}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]}>
        {content}
      </ReactMarkdown>
    </article>
  );
}
