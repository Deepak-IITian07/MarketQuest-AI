import { useEffect, useState } from "react";
import { getHealth } from "../services/api";

type State = "checking" | "online" | "offline";

export default function StatusBadge() {
  const [state, setState] = useState<State>("checking");

  useEffect(() => {
    getHealth()
      .then((h) => setState(h.status === "ok" ? "online" : "offline"))
      .catch(() => setState("offline"));
  }, []);

  const label = { checking: "Checking backend…", online: "Backend online", offline: "Backend offline" }[state];
  return <span className={`badge badge-${state}`}>{label}</span>;
}
