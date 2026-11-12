import { useEffect, useState, type ReactNode } from "react";
import {
  Activity,
  AudioLines,
  ChevronRight,
  Clapperboard,
  FolderClosed,
  GitBranch,
  HardDrive,
  Workflow,
  LayoutDashboard,
  Menu,
  Moon,
  RefreshCw,
  Rows3,
  Sun,
  UsersRound,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { IconButton } from "@/components/icon-button";
import { cn } from "@/lib/utils";
import type { Project, Section } from "@/types/monitor";

const sections = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "progress", label: "Production Progress", icon: Workflow },
  { id: "timeline", label: "Film timeline", icon: Rows3 },
  { id: "cast", label: "Cast sheets", icon: UsersRound },
  { id: "voices", label: "Voices", icon: AudioLines },
] as const;

interface ShellProps {
  projects: Project[];
  selected: string | null;
  project?: Project;
  section: Section;
  navigate: (section: Section) => void;
  selectProject: (id: string) => void;
  connected: boolean | null;
  refreshing: boolean;
  refresh: () => void;
  children: ReactNode;
}

function Sidebar({
  projects,
  selected,
  section,
  navigate,
  selectProject,
}: Pick<
  ShellProps,
  "projects" | "selected" | "section" | "navigate" | "selectProject"
>) {
  return (
    <div className="sidebar-inner">
      <div className="studio-brand">
        <span>
          <Clapperboard className="size-5" strokeWidth={1.5} />
        </span>
        <div>
          Story Film<span>STUDIO MONITOR</span>
        </div>
      </div>
      <div className="sidebar-group-title">WORKSPACE</div>
      <nav className="section-navigation" aria-label="Monitor sections">
        {sections.map((item) => (
          <Button
            variant="ghost"
            key={item.id}
            className={cn(
              "section-nav-button",
              section === item.id && "selected",
            )}
            onClick={() => navigate(item.id)}
            aria-current={section === item.id ? "page" : undefined}
          >
            <item.icon className="size-4" strokeWidth={1.7} />
            <span>{item.label}</span>
            {section === item.id && <span className="nav-active-mark" />}
          </Button>
        ))}
      </nav>
      <div className="sidebar-group-title mt-8!">
        PRODUCTIONS <span>{projects.length}</span>
      </div>
      <nav className="production-navigation" aria-label="Story projects">
        {projects.map((project) => (
          <Button
            key={project.id}
            variant="ghost"
            className={cn(
              "production-nav-button",
              selected === project.id && "selected",
            )}
            onClick={() => selectProject(project.id)}
          >
            <FolderClosed className="size-4" strokeWidth={1.5} />
            <span>{project.title}</span>
            {project.state === "running" && <span className="live-dot" />}
          </Button>
        ))}
        {!projects.length && (
          <p className="px-3 text-xs leading-5 text-muted-foreground">
            Your initialized stories will appear here.
          </p>
        )}
      </nav>
      <div className="sidebar-footer">
        <span className="workspace-avatar">
          <HardDrive className="size-4" />
        </span>
        <div>
          <strong>Local workspace</strong>
          <small>Production stays on this computer</small>
        </div>
      </div>
    </div>
  );
}

export function AppShell(props: ShellProps) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [dark, setDark] = useState(() => {
    try {
      return (
        localStorage.getItem("studio-theme") === "dark" ||
        (!localStorage.getItem("studio-theme") &&
          matchMedia("(prefers-color-scheme: dark)").matches)
      );
    } catch {
      return false;
    }
  });
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    try {
      localStorage.setItem("studio-theme", dark ? "dark" : "light");
    } catch {
      /* Storage may be disabled. */
    }
  }, [dark]);
  const sidebar = (
    <Sidebar
      {...props}
      navigate={(section) => {
        props.navigate(section);
        setMobileOpen(false);
      }}
      selectProject={(id) => {
        props.selectProject(id);
        setMobileOpen(false);
      }}
    />
  );
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to production
      </a>
      <aside className="desktop-sidebar">{sidebar}</aside>
      <div className="app-body">
        <header className="workspace-header">
          <div className="header-breadcrumb">
            <Dialog open={mobileOpen} onOpenChange={setMobileOpen}>
              <DialogTrigger
                render={
                  <Button
                    variant="ghost"
                    size="icon"
                    className="mobile-menu-button"
                    aria-label="Open navigation"
                  />
                }
              >
                <Menu className="size-5" />
              </DialogTrigger>
              <DialogContent className="mobile-navigation top-0 left-0 translate-x-0 translate-y-0">
                <DialogTitle className="sr-only">Studio navigation</DialogTitle>
                <DialogDescription className="sr-only">
                  Choose a production or monitor section.
                </DialogDescription>
                {sidebar}
              </DialogContent>
            </Dialog>
            <Clapperboard className="size-4 header-film-icon" />
            <span>Studio</span>
            <ChevronRight className="size-3.5 text-muted-foreground/50" />
            <strong>{props.project?.title || "Productions"}</strong>
            {props.project?.branch && (
              <Badge variant="outline" className="header-branch">
                <GitBranch className="size-3" />
                {props.project.branch}
              </Badge>
            )}
          </div>
          <div className="header-actions">
            <span
              className={cn(
                "connection-state",
                props.connected === false && "disconnected",
              )}
            >
              <span className="live-dot" />
              {props.connected === true
                ? "Live"
                : props.connected === false
                  ? "Reconnecting"
                  : "Connecting"}
            </span>
            <span className="header-divider" />
            <IconButton
              label={dark ? "Switch to light theme" : "Switch to dark theme"}
              onClick={() => setDark((value) => !value)}
            >
              {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
            </IconButton>
            <IconButton
              label="Refresh production records"
              onClick={props.refresh}
              disabled={props.refreshing}
            >
              <RefreshCw
                className={cn(
                  "size-4",
                  props.refreshing &&
                    props.connected !== true &&
                    "motion-safe:animate-spin",
                )}
              />
            </IconButton>
          </div>
        </header>
        {props.connected === false && (
          <div className="connection-notice" role="status">
            <Activity className="size-4" />
            <span>
              Connection interrupted. Showing the last snapshot while the
              monitor reconnects.
            </span>
          </div>
        )}
        <main id="main-content" className="main-content">
          {props.children}
        </main>
      </div>
    </div>
  );
}
