import { Fragment, useEffect, useMemo, useState } from "react";
import {
  createColumnHelper,
  createPaginatedRowModel,
  createSortedRowModel,
  rowPaginationFeature,
  rowSortingFeature,
  sortFns,
  tableFeatures,
  useTable,
} from "@tanstack/react-table";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ArrowUpRight,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Search,
} from "lucide-react";
import { SectionPanel } from "@/components/section-panel";
import { SelectField } from "@/components/select-field";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { duration, partLabel, stateLabels, timestamp } from "@/lib/format";
import { orderedJobs } from "@/lib/selectors";
import { cn } from "@/lib/utils";
import type { Job, MonitorSnapshot } from "@/types/monitor";

const features = tableFeatures({
  rowSortingFeature,
  rowPaginationFeature,
  sortedRowModel: createSortedRowModel(),
  paginatedRowModel: createPaginatedRowModel(),
  sortFns,
});
const helper = createColumnHelper<typeof features, Job>();
const columns = helper.columns([
  helper.accessor("label", {
    id: "stage",
    header: "Stage",
    cell: (context) => (
      <span className="datatable-stage-label">{context.getValue()}</span>
    ),
  }),
  helper.accessor("state", {
    header: "Status",
    cell: (context) => <StatusBadge state={context.getValue()} />,
  }),
  helper.accessor((row) => row.part || "", {
    id: "part",
    header: "Part",
    cell: (context) => (
      <span className="table-time">
        {context.getValue() ? partLabel(context.getValue()) : "Studio"}
      </span>
    ),
  }),
  helper.accessor(
    (row) => (row.started_at ? Date.parse(row.started_at) : undefined),
    {
      id: "started",
      header: "Started",
      sortUndefined: "last",
      cell: (context) => (
        <span className="table-time">
          {context.row.original.started_at
            ? timestamp(context.row.original.started_at)
            : "—"}
        </span>
      ),
    },
  ),
  helper.accessor(
    (row) => (row.finished_at ? Date.parse(row.finished_at) : undefined),
    {
      id: "finished",
      header: "Finished",
      sortUndefined: "last",
      cell: (context) => (
        <span className="table-time">
          {context.row.original.finished_at
            ? timestamp(context.row.original.finished_at)
            : context.row.original.state === "running"
              ? "Running"
              : "—"}
        </span>
      ),
    },
  ),
  helper.accessor((row) => row.elapsed_seconds ?? undefined, {
    id: "duration",
    header: "Duration",
    sortUndefined: "last",
    cell: (context) => (
      <span className="table-time">
        {context.row.original.state === "cached"
          ? "Reused"
          : context.getValue() == null
            ? "—"
            : duration(context.getValue(), true)}
      </span>
    ),
  }),
]);

export function StageTable({
  snapshot,
  onProgress,
}: {
  snapshot: MonitorSnapshot;
  onProgress: () => void;
}) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [expanded, setExpanded] = useState<string | null>(null);
  const jobs = useMemo(() => orderedJobs(snapshot.jobs), [snapshot.jobs]);
  const data = useMemo(
    () =>
      jobs.filter(
        (job) =>
          (status === "all" || job.state === status) &&
          [job.label, job.part, job.id, job.message].some((value) =>
            value?.toLowerCase().includes(query.trim().toLowerCase()),
          ),
      ),
    [jobs, query, status],
  );
  const table = useTable({
    key: "production-stages",
    features,
    columns,
    data,
    getRowId: (row) => row.id || row.label,
    initialState: { pagination: { pageIndex: 0, pageSize: 10 } },
    autoResetPageIndex: false,
  });
  const pagination = table.state.pagination;
  const pageCount = table.getPageCount();
  useEffect(() => {
    if (pagination.pageIndex >= pageCount && pagination.pageIndex > 0)
      table.setPageIndex(Math.max(0, pageCount - 1));
  }, [pageCount, pagination.pageIndex, table]);
  const rows = table.getRowModel().rows;
  return (
    <SectionPanel
      title="Production tasks"
      action={
        <div className="flex items-center gap-2">
          <Badge variant="outline">{jobs.length} tasks</Badge>
          <Button variant="ghost" size="sm" onClick={onProgress}>
            Progress <ArrowUpRight className="size-3.5" />
          </Button>
        </div>
      }
      className="production-datatable"
      contentClassName="p-0!"
    >
      <div className="datatable-toolbar">
        <div className="search-field">
          <Search className="size-3.5" />
          <Input
            aria-label="Search production tasks"
            placeholder="Search tasks…"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              table.firstPage();
            }}
          />
        </div>
        <SelectField
          label="Filter task status"
          value={status}
          onChange={(value) => {
            setStatus(value);
            table.firstPage();
          }}
          options={[
            { value: "all", label: "All statuses" },
            ...[
              "running",
              "complete",
              "cached",
              "pending",
              "waiting",
              "provider_wait",
              "reported",
              "stale",
              "failed",
              "interrupted",
            ].map((value) => ({ value, label: stateLabels[value] })),
          ]}
        />
        {(query || status !== "all") && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setQuery("");
              setStatus("all");
              table.firstPage();
            }}
          >
            Clear
          </Button>
        )}
        <span className="datatable-result-count">
          {data.length} of {jobs.length} tasks
        </span>
      </div>
      <Table aria-label="Production task data table">
        <TableHeader>
          {table.getHeaderGroups().map((group) => (
            <TableRow key={group.id}>
              <TableHead className="datatable-expand-cell" />
              <TableHead className="datatable-index">#</TableHead>
              {group.headers.map((header) => {
                const direction = header.column.getIsSorted();
                const Icon =
                  direction === "asc"
                    ? ArrowUp
                    : direction === "desc"
                      ? ArrowDown
                      : ArrowUpDown;
                return (
                  <TableHead
                    key={header.id}
                    className={cn(header.id === "duration" && "numeric-cell")}
                    aria-sort={
                      direction === "asc"
                        ? "ascending"
                        : direction === "desc"
                          ? "descending"
                          : "none"
                    }
                  >
                    <Button
                      variant="ghost"
                      size="xs"
                      className="table-sort-button"
                      onClick={header.column.getToggleSortingHandler()}
                      aria-label={`Sort by ${String(header.column.columnDef.header)}`}
                    >
                      <table.FlexRender header={header} />
                      <Icon className="size-3 opacity-50" />
                    </Button>
                  </TableHead>
                );
              })}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {rows.map((row, index) => (
            <Fragment key={row.id}>
              <TableRow
                className={cn(expanded === row.id && "expanded-task-row")}
              >
                <TableCell className="datatable-expand-cell">
                  <Button
                    variant="ghost"
                    size="icon-xs"
                    aria-label={`${expanded === row.id ? "Hide" : "Show"} task details for ${row.original.label}`}
                    aria-expanded={expanded === row.id}
                    onClick={() =>
                      setExpanded((value) => (value === row.id ? null : row.id))
                    }
                  >
                    {expanded === row.id ? (
                      <ChevronDown className="size-3" />
                    ) : (
                      <ChevronRight className="size-3" />
                    )}
                  </Button>
                </TableCell>
                <TableCell className="datatable-index">
                  {String(
                    pagination.pageIndex * pagination.pageSize + index + 1,
                  ).padStart(2, "0")}
                </TableCell>
                {row.getAllCells().map((cell) => (
                  <TableCell
                    key={cell.id}
                    className={cn(
                      cell.column.id === "duration" && "numeric-cell",
                    )}
                  >
                    <table.FlexRender cell={cell} />
                  </TableCell>
                ))}
              </TableRow>
              {expanded === row.id && (
                <TableRow className="task-detail-row">
                  <TableCell colSpan={columns.length + 2}>
                    <div>
                      <span className="eyebrow">TASK RECORD</span>
                      <p>{row.original.message}</p>
                      <dl>
                        <div>
                          <dt>Task ID</dt>
                          <dd>{row.original.id}</dd>
                        </div>
                        <div>
                          <dt>Started</dt>
                          <dd>{timestamp(row.original.started_at, true)}</dd>
                        </div>
                        <div>
                          <dt>Finished</dt>
                          <dd>{timestamp(row.original.finished_at, true)}</dd>
                        </div>
                        <div>
                          <dt>Progress</dt>
                          <dd>
                            {row.original.total != null
                              ? `${row.original.completed || 0} / ${row.original.total} ${row.original.unit || ""}`
                              : "No count recorded"}
                          </dd>
                        </div>
                        <div>
                          <dt>Heartbeat</dt>
                          <dd>{timestamp(row.original.heartbeat_at, true)}</dd>
                        </div>
                        <div>
                          <dt>Record type</dt>
                          <dd>
                            {row.original.instrumented
                              ? "Instrumented task"
                              : "Legacy task record"}
                          </dd>
                        </div>
                      </dl>
                    </div>
                  </TableCell>
                </TableRow>
              )}
            </Fragment>
          ))}
          {!rows.length && (
            <TableRow>
              <TableCell colSpan={columns.length + 2}>
                <div className="table-empty">
                  <Search className="size-5" />
                  <strong>
                    {jobs.length
                      ? "No matching tasks"
                      : "No tasks recorded yet"}
                  </strong>
                  <span>
                    {jobs.length
                      ? "Change the search or status filter."
                      : "Tasks will appear as production runs."}
                  </span>
                </div>
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
      <div className="datatable-footer">
        <span>
          {data.length ? pagination.pageIndex * pagination.pageSize + 1 : 0}–
          {Math.min(
            (pagination.pageIndex + 1) * pagination.pageSize,
            data.length,
          )}{" "}
          of {data.length} tasks
        </span>
        <div className="pagination-controls">
          <span className="rows-label">Rows</span>
          <SelectField
            label="Tasks per page"
            value={String(pagination.pageSize)}
            onChange={(value) => table.setPageSize(Number(value))}
            options={[5, 10, 20, 50].map((value) => ({
              value: String(value),
              label: String(value),
            }))}
          />
          <span className="pagination-position">
            Page {pageCount ? pagination.pageIndex + 1 : 0} of {pageCount}
          </span>
          <Button
            variant="outline"
            size="icon-xs"
            aria-label="First task page"
            disabled={!table.getCanPreviousPage()}
            onClick={() => table.firstPage()}
          >
            <ChevronsLeft className="size-3.5" />
          </Button>
          <Button
            variant="outline"
            size="icon-xs"
            aria-label="Previous task page"
            disabled={!table.getCanPreviousPage()}
            onClick={() => table.previousPage()}
          >
            <ChevronLeft className="size-3.5" />
          </Button>
          <Button
            variant="outline"
            size="icon-xs"
            aria-label="Next task page"
            disabled={!table.getCanNextPage()}
            onClick={() => table.nextPage()}
          >
            <ChevronRight className="size-3.5" />
          </Button>
          <Button
            variant="outline"
            size="icon-xs"
            aria-label="Last task page"
            disabled={!table.getCanLastPage()}
            onClick={() => table.lastPage()}
          >
            <ChevronsRight className="size-3.5" />
          </Button>
        </div>
      </div>
    </SectionPanel>
  );
}
