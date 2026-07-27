import type { ReactNode } from "react";
import type { JsonRecord } from "../types";

export interface Column {
  key: string;
  label: string;
  render?: (value: unknown, row: JsonRecord) => ReactNode;
  align?: "left" | "right";
}

interface DataTableProps {
  columns: Column[];
  rows: JsonRecord[];
  emptyText?: string;
  rowKey?: (row: JsonRecord, index: number) => string;
}

export function DataTable({
  columns,
  rows,
  emptyText = "当前筛选条件下没有数据",
  rowKey = (_, index) => String(index),
}: DataTableProps) {
  if (!rows.length) return <div className="empty-state">{emptyText}</div>;
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key} className={column.align === "right" ? "align-right" : ""}>
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={rowKey(row, index)}>
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={column.align === "right" ? "align-right" : ""}
                >
                  {column.render
                    ? column.render(row[column.key], row)
                    : String(row[column.key] ?? "—")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

