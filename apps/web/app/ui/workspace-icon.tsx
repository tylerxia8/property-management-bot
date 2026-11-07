export type IconName =
  | "overview"
  | "rent"
  | "prospect"
  | "repair"
  | "review"
  | "statement"
  | "arrow"
  | "house";

const paths: Record<IconName, string> = {
  overview: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  rent: "M3 7h18v14H3z M3 7l3-4h12l3 4 M3 12h18 M9 16h6",
  prospect:
    "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8 M17 8h5 M19.5 5.5v5",
  repair:
    "M14.5 6.5a5 5 0 0 0-6.4 6.4L3 18a2.1 2.1 0 0 0 3 3l5.1-5.1a5 5 0 0 0 6.4-6.4L14 13l-3-3z",
  review: "M9 3H5v18h14V3h-4 M9 2h6v4H9z M8 13l3 3 5-6",
  statement: "M6 2h9l4 4v16H6z M14 2v5h5 M9 12h7 M9 16h7",
  arrow: "M5 12h14 M13 6l6 6-6 6",
  house: "M3 10l9-7 9 7 M5 9v12h14V9 M9 21v-8h6v8",
};

export default function Icon({
  name,
  className = "",
}: {
  name: IconName;
  className?: string;
}) {
  return (
    <svg
      className={className}
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name]} />
    </svg>
  );
}
