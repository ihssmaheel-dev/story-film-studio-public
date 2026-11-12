import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  BackgroundVariant,
  MarkerType,
  ReactFlow,
  ReactFlowProvider,
  useNodesInitialized,
  useReactFlow,
  type Edge,
} from "@xyflow/react";
import {
  Check,
  CircleAlert,
  Clock3,
  Focus,
  LoaderCircle,
  Maximize2,
  Search,
  Workflow,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { IconButton } from "@/components/icon-button";
import { SelectField } from "@/components/select-field";
import { Progress } from "@/components/ui/progress";
import { duration, partLabel, timestamp } from "@/lib/format";
import { taskDuration } from "@/lib/selectors";
import type { MonitorSnapshot } from "@/types/monitor";
import {
  buildProgressSteps,
  displayState,
  isActive,
  isDone,
  needsAttention,
  stepLayout,
  STEP_SIZE,
  type ProgressStep,
} from "./progress-model";
import { ProgressStepNode, type StepNode } from "./progress-step-node";
import { ProgressStepDrawer } from "./progress-step-drawer";
import "@xyflow/react/dist/style.css";
import "./progress-flow.css";

const nodeTypes = { productionStep: ProgressStepNode };

function ProgressCanvas({
  steps,
  selected,
  connected,
  query,
  filter,
  openDetails,
}: {
  steps: ProgressStep[];
  selected: string | null;
  connected: boolean;
  query: string;
  filter: string;
  openDetails: (id: string) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const [columns, setColumns] = useState(4);
  const flow = useReactFlow<StepNode>();
  const initialized = useNodesInitialized();
  const autoFit = useRef("");
  useEffect(() => {
    const observer = new ResizeObserver(([entry]) =>
      setColumns(
        entry.contentRect.width >= 1000
          ? 4
          : entry.contentRect.width >= 720
            ? 3
            : entry.contentRect.width >= 500
              ? 2
              : 1,
      ),
    );
    if (container.current) observer.observe(container.current);
    return () => observer.disconnect();
  }, []);
  const nodes = useMemo<StepNode[]>(
    () =>
      steps.map((step, index) => {
        const state = displayState(step.state, connected);
        const matches =
          (!query ||
            [step.title, step.message, step.part].some((value) =>
              value?.toLowerCase().includes(query.toLowerCase()),
            )) &&
          (filter === "all" ||
            (filter === "active" && isActive(state)) ||
            (filter === "done" && isDone(state)) ||
            (filter === "attention" && needsAttention(state)));
        return {
          id: step.id,
          type: "productionStep",
          position: stepLayout(index, columns),
          data: { step, connected, openDetails },
          selected: step.id === selected,
          draggable: false,
          connectable: false,
          focusable: false,
          ...STEP_SIZE,
          measured: STEP_SIZE,
          style: { ...STEP_SIZE, opacity: matches ? 1 : 0.3 },
        };
      }),
    [steps, columns, connected, selected, openDetails, query, filter],
  );
  const edges = useMemo<Edge[]>(
    () =>
      nodes.slice(1).map((node, index) => {
        const previous = nodes[index],
          vertical = previous.position.y !== node.position.y,
          right = node.position.x > previous.position.x;
        const active = isActive(displayState(node.data.step.state, connected));
        return {
          id: `edge:${previous.id}:${node.id}`,
          source: previous.id,
          target: node.id,
          sourceHandle: vertical
            ? "out-bottom"
            : right
              ? "out-right"
              : "out-left",
          targetHandle: vertical ? "in-top" : right ? "in-left" : "in-right",
          type: "smoothstep",
          animated: active,
          className: active ? "progress-edge-active" : "progress-edge",
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: 14,
            height: 14,
            color: "var(--border)",
          },
        };
      }),
    [nodes, connected],
  );
  const focusStep =
    steps.find((step) => step.isCurrent) ||
    steps.find((step) => isActive(step.state)) ||
    steps.find((step) => needsAttention(step.state)) ||
    steps.at(-1);
  useEffect(() => {
    if (
      !initialized ||
      !flow.viewportInitialized ||
      !steps.length ||
      autoFit.current === String(columns)
    )
      return;
    const target =
      columns <= 2
        ? steps
            .slice(
              Math.max(
                0,
                steps.findIndex((step) => step.id === focusStep?.id) -
                  (columns === 1 ? 2 : 3),
              ),
              steps.findIndex((step) => step.id === focusStep?.id) + 1,
            )
            .map((step) => ({ id: step.id }))
        : undefined;
    // Fit after React Flow has committed the new responsive node positions.
    // Polling must not reset a viewport that the user has moved.
    const frame = requestAnimationFrame(() => {
      autoFit.current = String(columns);
      void flow.fitView({
        nodes: target,
        padding: { top: "24px", right: "24px", bottom: "80px", left: "24px" },
        maxZoom: 1,
        duration: 0,
      });
    });
    return () => cancelAnimationFrame(frame);
  }, [initialized, columns, steps, focusStep, flow]);
  return (
    <div className="production-flow-canvas" ref={container}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodeClick={(_, node) => openDetails(node.id)}
        nodesDraggable={false}
        nodesConnectable={false}
        nodesFocusable={false}
        edgesFocusable={false}
        elementsSelectable={false}
        deleteKeyCode={null}
        minZoom={0.25}
        maxZoom={1.5}
        zoomOnScroll={false}
        zoomOnDoubleClick={false}
        panOnScroll
        panOnDrag
        aria-label="Production progress workflow"
        className="production-flow"
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={20}
          size={1}
          color="var(--border)"
        />
      </ReactFlow>
      <div className="progress-map-controls">
        <IconButton
          label="Zoom out progress flow"
          onClick={() => void flow.zoomOut({ duration: 150 })}
        >
          <ZoomOut className="size-4" />
        </IconButton>
        <IconButton
          label="Zoom in progress flow"
          onClick={() => void flow.zoomIn({ duration: 150 })}
        >
          <ZoomIn className="size-4" />
        </IconButton>
        <IconButton
          label="Fit all progress steps"
          onClick={() =>
            void flow.fitView({ padding: 0.16, maxZoom: 1, duration: 150 })
          }
        >
          <Maximize2 className="size-4" />
        </IconButton>
        <span />
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            if (focusStep)
              void flow.fitView({
                nodes: [{ id: focusStep.id }],
                padding: 1,
                maxZoom: 1,
                duration: 150,
              });
          }}
          disabled={!focusStep}
        >
          <Focus className="size-3.5" />
          {focusStep && (focusStep.isCurrent || isActive(focusStep.state))
            ? "Current step"
            : "Latest step"}
        </Button>
      </div>
      {!steps.length && (
        <div className="progress-map-empty">
          <Workflow className="size-7" />
          <h2>No progress recorded yet</h2>
          <p>
            Real tasks and production events will appear here as they are
            recorded.
          </p>
        </div>
      )}
    </div>
  );
}

export function ProductionProgress({
  snapshot,
  connected,
}: {
  snapshot: MonitorSnapshot;
  connected: boolean;
}) {
  const [part, setPart] = useState(
    snapshot.parts[0]?.id || snapshot.media[0]?.part || "project",
  );
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [selected, setSelected] = useState<string | null>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  const selectedPart = snapshot.parts.some((item) => item.id === part)
    ? part
    : snapshot.parts[0]?.id || part;
  const steps = useMemo(
    () => buildProgressSteps(snapshot, selectedPart),
    [snapshot, selectedPart],
  );
  const openDetails = useCallback((id: string) => {
    returnFocus.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    setSelected(id);
  }, []);
  const selectedStep = steps.find((step) => step.id === selected) || null;
  const active = steps.filter((step) =>
    isActive(displayState(step.state, connected)),
  );
  const done = steps.filter((step) => isDone(step.state));
  const currentState = displayState(snapshot.current.state, connected);
  const currentActive = isActive(currentState);
  const CurrentIcon = currentActive
    ? LoaderCircle
    : needsAttention(currentState)
      ? CircleAlert
      : done.length === steps.length && steps.length
        ? Check
        : Clock3;
  const currentStep =
    steps.find((step) => step.isCurrent) ||
    active[0] ||
    steps.find((step) => needsAttention(step.state));
  return (
    <section
      className="production-progress-view"
      aria-label="Production Progress"
    >
      <div className="progress-live-strip">
        <span className="progress-live-icon">
          <CurrentIcon
            className={
              currentActive ? "size-4 motion-safe:animate-spin" : "size-4"
            }
            data-testid={currentActive ? "current-progress-loader" : undefined}
          />
        </span>
        <div>
          <strong>
            {!connected
              ? "Showing the last recorded progress"
              : snapshot.current.label}
          </strong>
          <small>{snapshot.current.message}</small>
        </div>
        {snapshot.current.percent != null && (
          <div className="progress-current-meter">
            <span>
              {snapshot.current.completed} / {snapshot.current.total}{" "}
              {snapshot.current.unit}
              <strong>{Math.round(snapshot.current.percent)}%</strong>
            </span>
            <Progress
              value={snapshot.current.percent}
              aria-label="Current task measured progress"
            />
          </div>
        )}
        <div className="progress-strip-meta">
          <strong>
            {done.length}/{steps.length} recorded steps
          </strong>
          <small>
            {active.length ? `${active.length} active` : "No live task"} ·{" "}
            {duration(taskDuration(snapshot.events), true)} measured work
          </small>
        </div>
      </div>
      <div className="progress-flow-panel">
        <div className="progress-flow-toolbar">
          <div className="search-field">
            <Search className="size-3.5" />
            <Input
              aria-label="Find a progress step"
              placeholder="Find a step…"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
          <SelectField
            label="Filter progress steps"
            value={filter}
            onChange={setFilter}
            options={[
              { value: "all", label: "All steps" },
              { value: "active", label: "Active steps" },
              { value: "done", label: "Completed steps" },
              { value: "attention", label: "Needs attention" },
            ]}
          />
          {(query || filter !== "all") && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setQuery("");
                setFilter("all");
              }}
            >
              Clear
            </Button>
          )}
          <div className="progress-toolbar-right">
            {snapshot.attention.length > 0 && currentStep && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => openDetails(currentStep.id)}
              >
                <CircleAlert className="size-3.5" />
                {snapshot.attention.length} open actions
              </Button>
            )}
            {snapshot.parts.length > 1 ? (
              <SelectField
                label="Progress part"
                value={selectedPart}
                onChange={(value) => {
                  setPart(value);
                  setSelected(null);
                }}
                options={snapshot.parts.map((item) => ({
                  value: item.id,
                  label: partLabel(item.id),
                }))}
              />
            ) : (
              <Badge variant="outline">
                {selectedPart === "project"
                  ? "Project"
                  : partLabel(selectedPart)}
              </Badge>
            )}
          </div>
        </div>
        <ReactFlowProvider key={`${snapshot.project.id}:${selectedPart}`}>
          <ProgressCanvas
            steps={steps}
            selected={selected}
            connected={connected}
            query={query.trim()}
            filter={filter}
            openDetails={openDetails}
          />
        </ReactFlowProvider>
        <div className="progress-flow-footer">
          <div>
            <span className="progress-legend-done" />
            Completed
            <span className="progress-legend-active" />
            Active
            <span className="progress-legend-waiting" />
            Waiting / attention
          </div>
          <span>
            Workflow order · Updated {timestamp(snapshot.observed_at)}
          </span>
        </div>
      </div>
      <p className="progress-flow-note">
        Select a step to inspect its current state, timings and recorded
        activity. Connections show workflow order; they are not a time scale.
      </p>
      <ProgressStepDrawer
        step={selectedStep}
        snapshot={snapshot}
        connected={connected}
        close={() => setSelected(null)}
        returnFocus={returnFocus}
      />
    </section>
  );
}
