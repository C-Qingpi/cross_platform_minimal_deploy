declare module "react-scroll-to-bottom" {
  import type { ReactNode } from "react";

  interface ScrollToBottomProps {
    checkInterval?: number;
    children?: ReactNode;
    className?: string;
    debounce?: number;
    debug?: boolean;
    followButtonClassName?: string;
    initialScrollBehavior?: "auto" | "smooth";
    mode?: "bottom" | "top";
    nonce?: string;
    scroller?: (props: {
      maxValue: number;
      minValue: number;
      offsetHeight: number;
      scrollHeight: number;
      scrollTop: number;
    }) => number;
    scrollViewClassName?: string;
  }

  interface ScrollPosition {
    scrollTop: number;
    scrollHeight: number;
    clientHeight: number;
  }

  const ScrollToBottom: React.FC<ScrollToBottomProps>;
  export default ScrollToBottom;

  export function useObserveScrollPosition(
    observer: ((position: ScrollPosition) => void) | null,
    deps?: unknown[],
  ): void;

  export function useSticky(): [boolean];
  export function useScrollTo(): (value: number | "100%", options?: { behavior?: "auto" | "smooth" }) => void;
  export function useScrollToBottom(): (options?: { behavior?: "auto" | "smooth" }) => void;
  export function useScrollToEnd(): (options?: { behavior?: "auto" | "smooth" }) => void;
  export function useScrollToTop(): (options?: { behavior?: "auto" | "smooth" }) => void;
  export function useScrollToStart(): (options?: { behavior?: "auto" | "smooth" }) => void;
  export function useAnimatingToEnd(): boolean;
  export function useAnimating(): boolean;
  export function useAtBottom(): boolean;
  export function useAtEnd(): boolean;
  export function useAtStart(): boolean;
  export function useAtTop(): boolean;
  export function useMode(): "bottom" | "top";

  export const FunctionContext: React.Context<{
    scrollTo: (value: number | "100%", options?: { behavior?: "auto" | "smooth" }) => void;
    scrollToBottom: (options?: { behavior?: "auto" | "smooth" }) => void;
    scrollToEnd: (options?: { behavior?: "auto" | "smooth" }) => void;
    scrollToStart: (options?: { behavior?: "auto" | "smooth" }) => void;
    scrollToTop: (options?: { behavior?: "auto" | "smooth" }) => void;
  }>;

  export const StateContext: React.Context<{
    atBottom: boolean;
    atEnd: boolean;
    atStart: boolean;
    atTop: boolean;
    animating: boolean;
    animatingToEnd: boolean;
    mode: "bottom" | "top";
    sticky: boolean;
  }>;
}
