import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { btn } from "./ui";
import { styles } from "../styles/styles";
import { cli } from "../lib/cli";

type EditionChoice = "java" | "bedrock" | "both";
type WizardStep = "edition" | "version" | "software" | "details";

type CreateServerWizardProps = {
  addLog: (level: "info" | "ok" | "warn" | "err", msg: string) => void;
  onClose: () => void;
  onInstalled: () => Promise<void>;
};

type CliStreamEventPayload = {
  stream_id?: string;
  streamId?: string;
  payload?: {
    event?: string;
    level?: string;
    message?: string;
    msg?: string;
    progress?: number;
    percent?: number;
    pct?: number;
    [key: string]: unknown;
  };
  event?: string;
  level?: string;
  message?: string;
  msg?: string;
  progress?: number;
  percent?: number;
  pct?: number;
};

const BEDROCK_PLATFORM = "bedrock";
const BEDROCK_VERSION = "1.21.132.3";

const BOTH_COMPATIBLE_PLATFORMS = new Set(["paper", "purpur", "pufferfish", "folia", "spigot", "craftbukkit"]);

const SOFTWARE_DESCRIPTIONS: Record<string, string> = {
  paper: "Fast and stable Bukkit-compatible server. Good default.",
  purpur: "Paper fork with many gameplay tuning options.",
  pufferfish: "Paper fork focused on aggressive performance optimizations.",
  folia: "Regionized multi-threading. High performance, plugin compatibility varies.",
  spigot: "Classic Bukkit ecosystem server software.",
  craftbukkit: "Original Bukkit implementation with legacy plugin support.",
  fabric: "Lightweight mod loader for modern modpacks.",
  quilt: "Fabric-compatible mod loader fork with extra tooling.",
  forge: "Popular mod loader with broad mod ecosystem.",
  neoforge: "Modern Forge fork for newer-generation mods.",
  vanilla: "Official Minecraft server with no plugin API.",
  velocity: "Proxy software, not a standalone world server.",
  waterfall: "BungeeCord-compatible proxy for network setups.",
};

const PLATFORM_PRIORITY = [
  "paper",
  "purpur",
  "pufferfish",
  "folia",
  "spigot",
  "craftbukkit",
  "vanilla",
  "fabric",
  "quilt",
  "forge",
  "neoforge",
  "velocity",
  "waterfall",
];

function defaultServerName(edition: EditionChoice): string {
  if (edition === "bedrock") return "bedrock-server";
  if (edition === "both") return "geyser-server";
  return "java-server";
}

function sortPlatforms(platforms: string[]): string[] {
  const rank = new Map(PLATFORM_PRIORITY.map((p, idx) => [p, idx]));
  return [...platforms].sort((a, b) => {
    const ra = rank.get(a) ?? 9999;
    const rb = rank.get(b) ?? 9999;
    if (ra !== rb) return ra - rb;
    return a.localeCompare(b);
  });
}

function parseVersionTriplet(v: string): [number, number, number] {
  const m = v.match(/^(\d+)\.(\d+)\.(\d+)$/);
  if (!m) return [0, 0, 0];
  return [Number(m[1]) || 0, Number(m[2]) || 0, Number(m[3]) || 0];
}

function compareGameVersionsDesc(a: string, b: string): number {
  const aa = parseVersionTriplet(a);
  const bb = parseVersionTriplet(b);
  if (aa[0] !== bb[0]) return bb[0] - aa[0];
  if (aa[1] !== bb[1]) return bb[1] - aa[1];
  if (aa[2] !== bb[2]) return bb[2] - aa[2];
  return b.localeCompare(a);
}

function normalizeGameVersion(raw: string, platform: string): string | null {
  const trimmed = raw.trim().toLowerCase();

  // Common case: already starts with a Minecraft version token (e.g. "1.21.11", "1.20.1-47.3.0").
  const direct = trimmed.match(/^1\.(\d+)(?:\.(\d+))?(?=[^0-9]|$)/);
  if (direct) {
    const minor = Number(direct[1] ?? "0");
    const patch = Number(direct[2] ?? "0");
    if (Number.isFinite(minor) && Number.isFinite(patch)) return `1.${minor}.${patch}`;
    return null;
  }

  // Fallback: find an embedded MC token, but do not allow a preceding dot.
  // This avoids false matches inside NeoForge values like "20.2.12-beta" ("1.2" in ".12").
  const embedded = trimmed.match(/(?:^|[^0-9.])1\.(\d+)(?:\.(\d+))?(?=[^0-9]|$)/);
  if (embedded) {
    const minor = Number(embedded[1] ?? "0");
    const patch = Number(embedded[2] ?? "0");
    if (Number.isFinite(minor) && Number.isFinite(patch)) return `1.${minor}.${patch}`;
    return null;
  }

  // NeoForge uses shorthand like "21.11.37-beta" (maps to MC 1.21.11).
  if (platform === "neoforge") {
    const neo = trimmed.match(/^(\d{2})\.(\d+)(?:\.\d+)?(?:[^\d].*)?$/);
    if (!neo) return null;
    const mcMinor = Number(neo[1] ?? "0");
    const mcPatch = Number(neo[2] ?? "0");
    if (!Number.isFinite(mcMinor) || !Number.isFinite(mcPatch)) return null;
    if (mcMinor < 14 || mcMinor > 40) return null;
    if (mcPatch < 0 || mcPatch > 99) return null;
    return `1.${mcMinor}.${mcPatch}`;
  }

  return null;
}

function stepTitle(step: WizardStep): string {
  if (step === "edition") return "Choose Edition";
  if (step === "version") return "Choose Game Version";
  if (step === "software") return "Choose Server Software";
  return "Server Details";
}

export function CreateServerWizard({ addLog, onClose, onInstalled }: CreateServerWizardProps) {
  const [step, setStep] = useState<WizardStep>("edition");
  const [edition, setEdition] = useState<EditionChoice>("java");
  const [name, setName] = useState(defaultServerName("java"));
  const [ramMb, setRamMb] = useState("2048");
  const [eulaAccepted, setEulaAccepted] = useState(true);
  const [stickyAddress, setStickyAddress] = useState(true);

  const [hostOs, setHostOs] = useState<string>("");
  const [hostOsLoading, setHostOsLoading] = useState(false);

  const [catalogLoading, setCatalogLoading] = useState(false);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [allPlatforms, setAllPlatforms] = useState<string[]>([]);
  const [supportByGameVersion, setSupportByGameVersion] = useState<Record<string, string[]>>({});
  const [reloadNonce, setReloadNonce] = useState(0);

  const [versionQuery, setVersionQuery] = useState("");
  const [version, setVersion] = useState("");
  const [platform, setPlatform] = useState("");

  const [installing, setInstalling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [installPhase, setInstallPhase] = useState("Ready to install.");
  const [installProgress, setInstallProgress] = useState(0);
  const [installFeed, setInstallFeed] = useState<string[]>([]);

  const catalogLoadedRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    async function loadHostOs() {
      setHostOsLoading(true);
      try {
        const os = await invoke<string>("host_os");
        if (!cancelled) setHostOs(String(os || "").toLowerCase());
      } catch {
        if (!cancelled) setHostOs("");
      } finally {
        if (!cancelled) setHostOsLoading(false);
      }
    }
    void loadHostOs();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (edition === "bedrock") return;
    if (catalogLoadedRef.current && reloadNonce === 0) return;

    let cancelled = false;
    async function loadCatalog() {
      setCatalogLoading(true);
      setCatalogError(null);
      try {
        const platformRes = await cli<string[]>("get_platforms");
        const platformsRaw = Array.isArray(platformRes?.data) ? platformRes.data : [];
        const platforms = sortPlatforms(platformsRaw.map((p) => String(p)).filter(Boolean));

        const support = new Map<string, Set<string>>();

        const entries = await Promise.all(
          platforms.map(async (p) => {
            try {
              const res = await cli<string[]>("get_versions", p);
              const versions = Array.isArray(res?.data) ? res.data.map((v) => String(v)).filter(Boolean) : [];
              return [p, versions] as const;
            } catch {
              return [p, [] as string[]] as const;
            }
          }),
        );

        for (const [p, versions] of entries) {
          for (const raw of versions) {
            const gv = normalizeGameVersion(raw, p);
            if (!gv) continue;
            if (!support.has(gv)) support.set(gv, new Set());
            support.get(gv)?.add(p);
          }
        }

        if (cancelled) return;

        const byGameVersion: Record<string, string[]> = {};
        for (const [gv, set] of support.entries()) {
          byGameVersion[gv] = sortPlatforms(Array.from(set));
        }

        setAllPlatforms(platforms);
        setSupportByGameVersion(byGameVersion);
        catalogLoadedRef.current = true;
      } catch (e: any) {
        if (!cancelled) setCatalogError(String(e));
      } finally {
        if (!cancelled) setCatalogLoading(false);
      }
    }

    void loadCatalog();
    return () => {
      cancelled = true;
    };
  }, [edition, reloadNonce]);

  const availableGameVersions = useMemo(() => {
    if (edition === "bedrock") return [BEDROCK_VERSION];
    return Object.keys(supportByGameVersion).sort(compareGameVersionsDesc);
  }, [edition, supportByGameVersion]);

  const filteredGameVersions = useMemo(() => {
    const q = versionQuery.trim().toLowerCase();
    if (!q) return availableGameVersions;
    return availableGameVersions.filter((v) => v.toLowerCase().includes(q));
  }, [availableGameVersions, versionQuery]);

  const compatiblePlatforms = useMemo(() => {
    if (edition === "bedrock") return [BEDROCK_PLATFORM];
    if (!version) return [];
    const base = supportByGameVersion[version] ?? [];
    if (edition === "both") return base.filter((p) => BOTH_COMPATIBLE_PLATFORMS.has(p));
    return base;
  }, [edition, supportByGameVersion, version]);

  const softwareCountByVersion = useMemo(() => {
    const out: Record<string, number> = {};
    if (edition === "bedrock") {
      out[BEDROCK_VERSION] = 1;
      return out;
    }
    for (const [gv, list] of Object.entries(supportByGameVersion)) {
      out[gv] = edition === "both" ? list.filter((p) => BOTH_COMPATIBLE_PLATFORMS.has(p)).length : list.length;
    }
    return out;
  }, [edition, supportByGameVersion]);

  useEffect(() => {
    setError(null);
    setName((prev) => {
      const trimmed = prev.trim();
      if (!trimmed || trimmed === "java-server" || trimmed === "bedrock-server" || trimmed === "geyser-server") {
        return defaultServerName(edition);
      }
      return prev;
    });
  }, [edition]);

  useEffect(() => {
    if (edition === "bedrock") {
      setVersion(BEDROCK_VERSION);
      setPlatform(BEDROCK_PLATFORM);
      return;
    }

    if (version && !availableGameVersions.includes(version)) {
      setVersion("");
    }
  }, [edition, availableGameVersions, version]);

  useEffect(() => {
    if (edition === "bedrock") return;
    if (!version) {
      setPlatform("");
      return;
    }
    if (!compatiblePlatforms.includes(platform)) {
      setPlatform("");
    }
  }, [edition, version, compatiblePlatforms, platform]);

  useEffect(() => {
    setInstallPhase("Ready to install.");
    setInstallProgress(0);
    setInstallFeed([]);
  }, [edition, version, platform]);

  const bedrockBlocked = edition === "bedrock" && !hostOsLoading && hostOs !== "windows";
  const hasCatalog = edition === "bedrock" || allPlatforms.length > 0;

  const canInstall =
    !installing &&
    !!name.trim() &&
    !!version &&
    !!platform &&
    eulaAccepted &&
    !bedrockBlocked &&
    (!catalogLoading || edition === "bedrock");

  const totalSteps = edition === "bedrock" ? 2 : 4;
  const currentStepNumber =
    edition === "bedrock"
      ? step === "edition"
        ? 1
        : 2
      : step === "edition"
        ? 1
        : step === "version"
          ? 2
          : step === "software"
            ? 3
            : 4;
  const stepFlow: WizardStep[] = edition === "bedrock" ? ["edition", "details"] : ["edition", "version", "software", "details"];

  function pillStyle(active: boolean, done: boolean): CSSProperties {
    return {
      borderRadius: 999,
      border: active ? "1px solid rgba(56,189,248,.72)" : done ? "1px solid rgba(34,197,94,.45)" : "1px solid rgba(148,163,184,.28)",
      background: active
        ? "linear-gradient(135deg, rgba(56,189,248,.28), rgba(59,130,246,.2))"
        : done
          ? "rgba(34,197,94,.13)"
          : "rgba(15,23,42,.45)",
      color: "rgba(241,245,249,.95)",
      padding: "6px 10px",
      fontSize: 11,
      fontWeight: 850,
      letterSpacing: 0.2,
    };
  }

  function optionCardStyle(selected: boolean): CSSProperties {
    return {
      borderRadius: 14,
      border: selected ? "1px solid rgba(56,189,248,.72)" : "1px solid rgba(148,163,184,.24)",
      background: selected
        ? "linear-gradient(165deg, rgba(59,130,246,.26), rgba(30,41,59,.9))"
        : "linear-gradient(165deg, rgba(15,23,42,.86), rgba(2,6,23,.72))",
      color: "rgba(255,255,255,.94)",
      padding: "11px 12px",
      textAlign: "left",
      cursor: "pointer",
      boxShadow: selected ? "0 10px 24px rgba(2,132,199,.2)" : "none",
    };
  }

  const fieldInputStyle: CSSProperties = {
    ...styles.search,
    border: "1px solid rgba(148,163,184,.32)",
    background: "rgba(15,23,42,.52)",
    color: "rgba(248,250,252,.96)",
  };

  function bumpInstallProgress(next: number) {
    setInstallProgress((prev) => Math.max(prev, Math.min(100, next)));
  }

  function pushInstallFeed(line: string) {
    const trimmed = line.trim();
    if (!trimmed) return;
    setInstallFeed((prev) => {
      const next = [...prev, trimmed];
      return next.length > 12 ? next.slice(next.length - 12) : next;
    });
  }

  function updateInstallPhaseFromLog(line: string) {
    const msg = line.toLowerCase();
    const pctMatch = msg.match(/(?:^|\s)(\d{1,3})\s*%/);
    if (pctMatch) {
      const pct = Number(pctMatch[1]);
      if (Number.isFinite(pct)) {
        bumpInstallProgress(Math.max(20, Math.min(95, pct)));
      }
    }
    if (msg.includes("download")) {
      setInstallPhase("Downloading server files…");
      bumpInstallProgress(35);
      return;
    }
    if (msg.includes("extract") || msg.includes("unzip")) {
      setInstallPhase("Extracting files…");
      bumpInstallProgress(55);
      return;
    }
    if (msg.includes("write") || msg.includes("config") || msg.includes("properties")) {
      setInstallPhase("Writing config files…");
      bumpInstallProgress(72);
      return;
    }
    if (msg.includes("tunnel") || msg.includes("sync")) {
      setInstallPhase("Syncing network settings…");
      bumpInstallProgress(88);
      return;
    }
    if (msg.includes("done") || msg.includes("finish") || msg.includes("complete")) {
      setInstallPhase("Finalizing installation…");
      bumpInstallProgress(95);
    }
  }

  function startInstallProgressPulse(): () => void {
    const startedAt = Date.now();
    const timer = window.setInterval(() => {
      setInstallProgress((prev) => {
        if (prev >= 94) return prev;
        // Smooth non-linear ramp so long installs don't appear stuck.
        const elapsedMs = Date.now() - startedAt;
        const eased = 1 - Math.exp(-elapsedMs / 13000);
        const target = 8 + Math.floor(eased * 84);
        return Math.max(prev, Math.min(94, target));
      });
    }, 320);
    return () => window.clearInterval(timer);
  }

  function chooseEdition(next: EditionChoice) {
    setEdition(next);
    setError(null);
    setVersionQuery("");
    if (next === "bedrock") {
      setVersion(BEDROCK_VERSION);
      setPlatform(BEDROCK_PLATFORM);
      setStep("details");
      return;
    }
    setVersion("");
    setPlatform("");
    setStep("version");
  }

  function chooseVersion(v: string) {
    setVersion(v);
    setPlatform("");
    setError(null);
    setStep("software");
  }

  function choosePlatform(p: string) {
    setPlatform(p);
    setError(null);
    setStep("details");
  }

  function goBack() {
    if (installing) return;
    if (step === "details") {
      if (edition === "bedrock") setStep("edition");
      else setStep("software");
      return;
    }
    if (step === "software") {
      setStep("version");
      return;
    }
    if (step === "version") {
      setStep("edition");
    }
  }

  async function installServer() {
    setError(null);

    const serverName = name.trim();
    if (!serverName) {
      setError("Server name is required.");
      return;
    }

    const ramValue = Math.max(512, Number(ramMb) || 2048);
    if (!eulaAccepted) {
      setError("You must accept the EULA to install.");
      return;
    }
    if (bedrockBlocked) {
      setError("Bedrock installation is only available on Windows.");
      return;
    }

    let stopPulse: (() => void) | null = null;
    let unlistenFn: (() => void) | null = null;

    try {
      setInstalling(true);
      setInstallFeed([]);
      setInstallPhase("Starting installer…");
      setInstallProgress(8);
      addLog("info", `Installing ${edition} server "${serverName}" (${platform} ${version})…`);
      stopPulse = startInstallProgressPulse();

      const streamId = `install-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
      unlistenFn = await listen<CliStreamEventPayload>("cli_stream_event", (evt) => {
        const payload = evt.payload ?? {};
        const incomingStreamId =
          typeof payload.stream_id === "string"
            ? payload.stream_id
            : typeof payload.streamId === "string"
              ? payload.streamId
              : "";
        if (incomingStreamId !== streamId) return;

        const eventPayload = typeof payload.payload === "object" && payload.payload
          ? payload.payload
          : payload;
        const eventType = String(eventPayload.event ?? "");
        const message = String(eventPayload.message ?? eventPayload.msg ?? "");
        const rawProgress = eventPayload.progress ?? eventPayload.percent ?? eventPayload.pct;
        if (typeof rawProgress === "number" && Number.isFinite(rawProgress)) {
          bumpInstallProgress(Math.max(8, Math.min(95, rawProgress)));
        }

        if (eventType === "install_starting") {
          setInstallPhase("Preparing server files…");
          bumpInstallProgress(18);
          return;
        }

        if (eventType === "install_finished") {
          setInstallPhase("Finishing up…");
          bumpInstallProgress(96);
          return;
        }

        if (eventType === "log") {
          if (message) {
            pushInstallFeed(message);
            updateInstallPhaseFromLog(message);
          }
          return;
        }

        if (eventType === "error") {
          if (message) pushInstallFeed(`Error: ${message}`);
          setInstallPhase("Install failed.");
          return;
        }

        if (eventType === "result") {
          setInstallPhase("Install complete.");
          bumpInstallProgress(100);
        }
      });

      await invoke("run_cli_json_stream", {
        args: [
          "install_server",
          edition,
          platform,
          version,
          serverName,
          String(ramValue),
          eulaAccepted ? "true" : "false",
          stickyAddress ? "true" : "false",
        ],
        streamId,
      });

      setInstallPhase("Install complete.");
      setInstallProgress(100);
      addLog("ok", `Installed "${serverName}".`);
      await onInstalled();
      onClose();
    } catch (e: any) {
      const msg = String(e);
      setError(msg);
      setInstallPhase("Install failed.");
      pushInstallFeed(`Error: ${msg}`);
      addLog("err", `Install failed: ${msg}`);
    } finally {
      if (unlistenFn) {
        try {
          unlistenFn();
        } catch {
          // ignore cleanup errors
        }
      }
      if (stopPulse) {
        try {
          stopPulse();
        } catch {
          // ignore cleanup errors
        }
      }
      setInstalling(false);
    }
  }

  function platformDescription(p: string): string {
    return SOFTWARE_DESCRIPTIONS[p] ?? "Minecraft server software.";
  }

  return (
    <div
      style={{
        width: "min(880px, 100%)",
        borderRadius: 22,
        border: "1px solid rgba(148,163,184,.24)",
        background:
          "radial-gradient(900px 500px at -5% -20%, rgba(56,189,248,.14), transparent 58%), radial-gradient(850px 520px at 105% 10%, rgba(59,130,246,.12), transparent 56%), rgba(2,6,23,.96)",
        boxShadow: "0 34px 90px rgba(0,0,0,.7)",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: 14,
          padding: "16px 18px",
          borderBottom: "1px solid rgba(148,163,184,.2)",
          background: "linear-gradient(180deg, rgba(15,23,42,.75), rgba(15,23,42,.35))",
        }}
      >
        <div>
          <div style={{ fontSize: 18, fontWeight: 950, letterSpacing: 0.2 }}>Create Server Wizard</div>
          <div style={{ fontSize: 12, opacity: 0.78, marginTop: 2 }}>
            Step {currentStepNumber} of {totalSteps} • {stepTitle(step)}
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 7, marginTop: 10 }}>
            {stepFlow.map((s, idx) => {
              const isActive = s === step;
              const isDone = idx < currentStepNumber - 1;
              return (
                <div key={s} style={pillStyle(isActive, isDone)}>
                  {idx + 1}. {stepTitle(s)}
                </div>
              );
            })}
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {step !== "edition" && (
            <button type="button" style={btn("ghost")} onClick={goBack} disabled={installing}>
              Back
            </button>
          )}
          <button type="button" style={btn("ghost")} onClick={onClose} disabled={installing}>Close</button>
        </div>
      </div>

      <div style={{ padding: 18, display: "grid", gap: 14 }}>
        {step === "edition" && (
          <div style={{ display: "grid", gap: 10 }}>
            <div style={{ fontSize: 13, fontWeight: 900 }}>Pick an edition</div>
            <div style={{ display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
              {([
                ["java", "Java", "Plugin/mod server (Paper/Fabric/Forge/etc)."],
                ["bedrock", "Bedrock", "Dedicated Bedrock server (Windows only)."],
                ["both", "Both (Geyser)", "Java server with Geyser bridge for Bedrock clients."],
              ] as const).map(([id, label, desc]) => (
                <button
                  key={id}
                  type="button"
                  style={optionCardStyle(edition === id)}
                  onClick={() => chooseEdition(id)}
                  disabled={installing}
                >
                  <div style={{ fontWeight: 900, fontSize: 13 }}>{label}</div>
                  <div style={{ fontSize: 12, opacity: 0.78, marginTop: 4 }}>{desc}</div>
                </button>
              ))}
            </div>
          </div>
        )}

        {step === "version" && (
          <div style={{ display: "grid", gap: 10 }}>
            <div style={{ fontSize: 13, fontWeight: 900 }}>Pick a Minecraft game version</div>
            {catalogLoading ? (
              <div style={styles.contentItemMeta}>Loading game versions…</div>
            ) : catalogError ? (
              <div style={{ ...styles.consoleError, marginTop: 0 }}>
                Failed to load versions: {catalogError}
                <div style={{ marginTop: 8 }}>
                  <button type="button" style={btn("ghost")} onClick={() => { catalogLoadedRef.current = false; setReloadNonce((x) => x + 1); }}>
                    Retry
                  </button>
                </div>
              </div>
            ) : !hasCatalog || availableGameVersions.length === 0 ? (
              <div style={{ ...styles.contentItemMeta, color: "rgba(252,165,165,.95)" }}>
                No Minecraft game versions available right now.
              </div>
            ) : (
              <>
                <input
                  style={fieldInputStyle}
                  placeholder="Filter versions…"
                  value={versionQuery}
                  onChange={(e) => setVersionQuery(e.target.value)}
                  disabled={installing}
                />
                <div
                  style={{
                    display: "grid",
                    gap: 9,
                    gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))",
                    maxHeight: 330,
                    overflowY: "auto",
                    paddingRight: 4,
                  }}
                >
                  {filteredGameVersions.map((v) => (
                    <button
                      key={v}
                      type="button"
                      onClick={() => chooseVersion(v)}
                      style={{
                        ...optionCardStyle(version === v),
                        padding: "9px 8px",
                        textAlign: "center",
                        minHeight: 62,
                      }}
                    >
                      <div style={{ fontWeight: 900, fontSize: 12 }}>{v}</div>
                      <div style={{ marginTop: 3, fontSize: 11, opacity: 0.72 }}>
                        {softwareCountByVersion[v] ?? 0} software option{(softwareCountByVersion[v] ?? 0) === 1 ? "" : "s"}
                      </div>
                    </button>
                  ))}
                </div>
                <div style={styles.contentItemMeta}>Selecting a version auto-advances to software selection.</div>
              </>
            )}
          </div>
        )}

        {step === "software" && (
          <div style={{ display: "grid", gap: 10 }}>
            <div style={{ fontSize: 13, fontWeight: 900 }}>Pick software for Minecraft {version}</div>
            {compatiblePlatforms.length === 0 ? (
              <div style={{ ...styles.contentItemMeta, color: "rgba(252,165,165,.95)" }}>
                No software supports this game version for the chosen edition.
              </div>
            ) : (
              <div style={{ display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
                {compatiblePlatforms.map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => choosePlatform(p)}
                    style={optionCardStyle(platform === p)}
                  >
                    <div style={{ fontWeight: 900, fontSize: 13 }}>{p}</div>
                    <div style={{ fontSize: 12, opacity: 0.78, marginTop: 4 }}>{platformDescription(p)}</div>
                  </button>
                ))}
              </div>
            )}
            {edition === "both" && (
              <div style={styles.contentItemMeta}>
                Both edition installs Java + Geyser plugin. Only Bukkit-style software is listed.
              </div>
            )}
            <div style={styles.contentItemMeta}>Selecting software auto-advances to final details.</div>
          </div>
        )}

        {step === "details" && (
          <div style={{ display: "grid", gap: 12 }}>
            <div
              style={{
                ...styles.contentItem,
                alignItems: "start",
                border: "1px solid rgba(148,163,184,.25)",
                background: "linear-gradient(165deg, rgba(15,23,42,.9), rgba(2,6,23,.7))",
              }}
            >
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={styles.contentItemTitle}>Install summary</div>
                <div style={styles.contentItemMeta}>Edition: {edition}</div>
                <div style={styles.contentItemMeta}>Game version: {version}</div>
                <div style={styles.contentItemMeta}>Software: {platform}</div>
              </div>
            </div>

            {edition === "bedrock" && (
              <div
                style={{
                  ...styles.contentItem,
                  alignItems: "start",
                  border: "1px solid rgba(148,163,184,.25)",
                  background: "linear-gradient(165deg, rgba(15,23,42,.9), rgba(2,6,23,.7))",
                }}
              >
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={styles.contentItemTitle}>Bedrock host check</div>
                  {hostOsLoading ? (
                    <div style={styles.contentItemMeta}>Checking operating system…</div>
                  ) : hostOs === "windows" ? (
                    <div style={styles.contentItemMeta}>Windows detected. Bedrock install is available.</div>
                  ) : (
                    <div style={{ ...styles.contentItemMeta, color: "rgba(252,165,165,.95)" }}>
                      Bedrock install is only supported on Windows. Detected OS: {hostOs || "unknown"}.
                    </div>
                  )}
                </div>
              </div>
            )}

            <div style={{ display: "grid", gap: 8 }}>
              <div style={{ fontSize: 13, fontWeight: 900 }}>Server name</div>
              <input
                style={fieldInputStyle}
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="my-server"
                disabled={installing}
              />
            </div>

            <div style={{ display: "grid", gap: 8 }}>
              <div style={{ fontSize: 13, fontWeight: 900 }}>RAM (MB)</div>
              <input
                style={fieldInputStyle}
                type="number"
                min={512}
                step={256}
                value={ramMb}
                onChange={(e) => setRamMb(e.target.value)}
                disabled={installing}
              />
            </div>

            <div
              style={{
                borderRadius: 14,
                border: "1px solid rgba(148,163,184,.28)",
                background: "linear-gradient(165deg, rgba(15,23,42,.82), rgba(2,6,23,.58))",
                padding: 12,
                display: "grid",
                gap: 8,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
                <div style={{ fontSize: 13, fontWeight: 900 }}>Install progress</div>
                <div style={{ fontSize: 12, opacity: 0.78 }}>{installPhase}</div>
              </div>
              <div
                style={{
                  height: 9,
                  borderRadius: 999,
                  border: "1px solid rgba(148,163,184,.28)",
                  background: "rgba(15,23,42,.7)",
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    width: `${installProgress}%`,
                    height: "100%",
                    borderRadius: 999,
                    background: "linear-gradient(90deg, rgba(56,189,248,.9), rgba(59,130,246,.9))",
                    transition: "width 220ms ease",
                  }}
                />
              </div>
              <div style={{ fontSize: 11, opacity: 0.7 }}>{Math.round(installProgress)}%</div>
              {installFeed.length > 0 && (
                <div
                  style={{
                    marginTop: 2,
                    maxHeight: 120,
                    overflowY: "auto",
                    borderRadius: 10,
                    border: "1px solid rgba(148,163,184,.2)",
                    background: "rgba(2,6,23,.55)",
                    padding: "8px 10px",
                    display: "grid",
                    gap: 5,
                  }}
                >
                  {installFeed.map((line, idx) => (
                    <div key={`${line}-${idx}`} style={{ fontSize: 11, opacity: 0.86 }}>
                      {line}
                    </div>
                  ))}
                </div>
              )}
            </div>

            <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <input type="checkbox" checked={eulaAccepted} onChange={(e) => setEulaAccepted(e.target.checked)} disabled={installing} />
              <span style={{ fontSize: 13, fontWeight: 800 }}>I accept the Minecraft server EULA.</span>
            </label>

            <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <input type="checkbox" checked={stickyAddress} onChange={(e) => setStickyAddress(e.target.checked)} disabled={installing} />
              <span style={{ fontSize: 13, fontWeight: 800 }}>Reserve a sticky public address for this server.</span>
            </label>

            {error && <div style={{ ...styles.consoleError, marginTop: 0 }}>Install error: {error}</div>}

            <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
              <button type="button" style={btn("ghost")} onClick={onClose} disabled={installing}>Cancel</button>
              <button type="button" style={btn("primary")} onClick={() => void installServer()} disabled={!canInstall}>
                {installing ? "Installing…" : "Install Server"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
