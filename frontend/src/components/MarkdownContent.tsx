import { useMemo } from "react";
import MarkdownPreview from "@uiw/react-markdown-preview";
import type { Components } from "react-markdown";
import rehypeSanitize from "rehype-sanitize";

interface MarkdownContentProps {
  content: string;
  className?: string;
}

/**
 * Agent message markdown renderer.
 * Uses @uiw/react-markdown-preview — GitHub-style rendering with
 * built-in copy buttons, syntax highlighting, and table handling.
 *
 * Tables are wrapped in a scrollable div so column sizing uses the
 * browser's native table-layout algorithm (not the library's display:block).
 */
export function MarkdownContent({ content, className = "" }: MarkdownContentProps) {
  const components = useMemo<Components>(
    () => ({
      table: ({ children, ...props }) => (
        <div className="md-table-wrap">
          <table {...props}>{children}</table>
        </div>
      ),
    }),
    [],
  );

  if (!content.trim()) return null;

  return (
    <div className={className} data-color-mode="light">
      <MarkdownPreview
        source={content}
        components={components}
        rehypePlugins={[rehypeSanitize]}
        wrapperElement={{
          "data-color-mode": "light",
        }}
      />
    </div>
  );
}
