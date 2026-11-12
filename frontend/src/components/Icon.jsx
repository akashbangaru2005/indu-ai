import React from "react";

const paths = {
  grid: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  mic: "M12 15a3 3 0 0 0 3-3V5a3 3 0 0 0-6 0v7a3 3 0 0 0 3 3ZM5 11v1a7 7 0 0 0 14 0v-1M12 19v3M8 22h8",
  message: "M21 11.5a8.5 8.5 0 0 1-8.5 8.5H4l-3 2V11.5a10 10 0 1 1 20 0ZM7 10h10M7 14h6",
  whatsapp: "M21 11.5a9 9 0 0 1-13.4 7.8L3 21l1.7-4.6A9 9 0 1 1 21 11.5ZM8 7c0 4.5 2.5 7 7 8l1-2-2-1-1 1c-2-1-3-2-3-3l1-1-1-2H8Z",
  arrow: "M5 12h14M13 6l6 6-6 6",
  send: "m22 2-7 20-4-9-9-4 20-7ZM22 2 11 13",
  close: "m6 6 12 12M6 18 18 6",
  plus: "M12 5v14M5 12h14",
  users: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M16 3a4 4 0 0 1 0 8M22 21v-2a4 4 0 0 0-3-3.87M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z",
  spark: "m12 2 3 7 7 3-7 3-3 7-3-7-7-3 7-3 3-7Z",
  globe: "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM3 12h18M12 3a18 18 0 0 1 0 18 18 18 0 0 1 0-18Z",
  check: "m5 12 4 4L19 6",
  cpu: "M6 6h12v12H6zM9 9h6v6H9zM9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4",
  volume: "m11 5-6 4H2v6h3l6 4V5ZM15 8a6 6 0 0 1 0 8M18 5a10 10 0 0 1 0 14",
  power: "M12 2v10M5 5a9 9 0 1 0 14 0",
  stop: "M6 6h12v12H6z",
  trash: "M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7",
  history: "M3 11a9 9 0 1 1 2 7M3 4v7h7M12 7v5l3 2",
};

export default function Icon({name, size = 20, ...props}) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}><path d={paths[name] || paths.spark}/></svg>;
}
