import type { JSX } from "preact";

type IconProps = JSX.SVGAttributes<SVGSVGElement>;

const baseProps = {
  fill: "none",
  stroke: "currentColor",
  strokeLinecap: "round",
  strokeLinejoin: "round",
  strokeWidth: 1.8,
  viewBox: "0 0 24 24",
} satisfies Partial<IconProps>;

export function RefreshIcon(props: IconProps) {
  return (
    <svg {...baseProps} {...props}>
      <path d="M20 5v5h-5" />
      <path d="M4 19v-5h5" />
      <path d="M18.2 9A7 7 0 0 0 6.8 6.6L4 9" />
      <path d="M5.8 15A7 7 0 0 0 17.2 17.4L20 15" />
    </svg>
  );
}

export function TrashIcon(props: IconProps) {
  return (
    <svg {...baseProps} {...props}>
      <path d="M4 7h16" />
      <path d="M10 11v6" />
      <path d="M14 11v6" />
      <path d="M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12" />
      <path d="M9 7V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v3" />
    </svg>
  );
}

export function MoreIcon(props: IconProps) {
  return (
    <svg {...baseProps} {...props}>
      <circle cx="12" cy="5" r="1.6" fill="currentColor" stroke="none" />
      <circle cx="12" cy="12" r="1.6" fill="currentColor" stroke="none" />
      <circle cx="12" cy="19" r="1.6" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function PlusIcon(props: IconProps) {
  return (
    <svg {...baseProps} {...props}>
      <path d="M12 5v14" />
      <path d="M5 12h14" />
    </svg>
  );
}

export function FolderIcon(props: IconProps) {
  return (
    <svg {...baseProps} {...props}>
      <path d="M3 7.5a2.5 2.5 0 0 1 2.5-2.5h4l2 2h7a2.5 2.5 0 0 1 2.5 2.5v7A2.5 2.5 0 0 1 18.5 19h-13A2.5 2.5 0 0 1 3 16.5z" />
    </svg>
  );
}

export function ModelIcon(props: IconProps) {
  return (
    <svg {...baseProps} {...props}>
      <path d="M7 6h10" />
      <path d="M7 12h10" />
      <path d="M7 18h10" />
      <circle cx="9" cy="6" r="1.5" fill="currentColor" stroke="none" />
      <circle cx="15" cy="12" r="1.5" fill="currentColor" stroke="none" />
      <circle cx="12" cy="18" r="1.5" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function SendIcon(props: IconProps) {
  return (
    <svg {...baseProps} {...props}>
      <path d="M4 20l16-8L4 4l3.5 8z" />
      <path d="M7.5 12H20" />
    </svg>
  );
}

export function LogoIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 163 26" fill="#7a7a7a" {...props}>
      <path d="m138.7 15.3c0.8 1.2 1.6 2.4 2.5 3.7h-2.7c-0.8-1-1.6-2.2-2.4-3.3h-3.1v3.3h-2.1v-11.3q1.8 0 3.6 0c1 0 2-0.1 3 0.1 1.6 0.2 2.8 1.1 3.2 2.7 0.3 1.7 0 3.3-1.5 4.4-0.2 0.1-0.3 0.2-0.5 0.4zm-5.7-1.7c1.5 0 2.8 0 4.2-0.1 0.9 0 1.3-0.7 1.3-1.6 0-1-0.4-1.7-1.3-1.8-1.4-0.2-2.8-0.1-4.2-0.1zm-29-5.8v1.6c-2.2 2.5-4.4 5-6.7 7.6h6.7v2.1h-9.6v-2.2c2-2.2 4-4.4 6.2-6.9h-6.2v-2.2zm-48.2-0.7c2.8 2.7 5.3 5.2 8 7.9v-6.5h2v11.4c-2.7-2.6-5.2-5.1-8-7.8v6.8h-2zm94.6 9.3c0.6-0.3 1.4-0.7 1.9-0.9 1.7 2.3 4.4 1.8 5.6 0.7 1.1-1 1.5-2.5 1-4-0.5-1.4-1.8-2.6-3.6-2.5-1.8 0.1-3.4 1.4-3.6 3.5h-2.1c0-2.1 1.5-4.6 3.9-5.3 3.1-0.9 6.1 0.6 7.3 3.5 1 2.8-0.2 5.9-3 7.2-2.6 1.3-6 0.3-7.4-2.2zm-120.5-6.3c-0.5 0.3-1.1 0.7-1.5 1-2.3-1.9-5-1.3-6 1.2-0.5 1.6 0.3 3.7 2.1 4.3 1.5 0.6 3.2 0 3.6-1.3-0.3-0.1-0.7-0.2-1.1-0.3-0.1-0.6-0.1-1.1-0.2-1.8h4.1c0.3 2.4-1.6 5-4 5.6-2.6 0.7-5.4-0.8-6.4-3.4-0.9-2.5 0.2-5.5 2.6-6.7 2.4-1.3 5.4-0.7 6.8 1.4zm-22.4-2.3c2 3.8 3.9 7.5 5.9 11.2h-2.3q-1.8-3.2-3.6-6.6c-1.3 2.3-2.4 4.4-3.6 6.6h-2.3c2-3.7 3.9-7.4 5.9-11.2zm69.1 2.5h-3.8v-1.9h9.5v1.9h-3.6v8.7h-2.1zm38.9-0.4v2.7l2.7 0.1c0 0 0 1.2 0 2.1-1.1 0-2.3 0-3.3-0.2-0.9-0.2-1.6-1-1.6-2-0.1-1.5 0-3.2 0-4.8h9.1v2.1zm-2.2 9.2v-2.9c0.5 0 1.1-0.1 1.7-0.1 0.1 0.3 0.1 0.9 0.4 0.9 0.3 0 4.5 0 6.9 0v2.1zm-71.9-8.7v2.6h2.5c0 0 0 1.2 0 2-1 0-2.1 0-3.1-0.2-0.8-0.2-1.4-0.9-1.5-1.8q0-2.2 0-4.5h8.5v1.9zm-2.1 8.5v-2.6c0.6-0.1 1.1-0.1 1.6-0.1 0.2 0.3 0.2 0.8 0.4 0.8 0.3 0 4.2 0 6.4 0v1.9z" />
    </svg>
  );
}
