"use client";

import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button, Empty, PageHeader, Panel } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { tenantApi } from "@/lib/api";
import { getMessages } from "@/messages";

export default function AnswersPage() {
  const { tenantId } = useParams<{ tenantId: string }>();
  const m = getMessages();
  const { user } = useAuth();
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [category, setCategory] = useState("demo");
  const [subcategory, setSubcategory] = useState("");
  const [answer, setAnswer] = useState("");
  const [question, setQuestion] = useState("");
  const [officeId, setOfficeId] = useState("");

  const entries = useQuery({
    queryKey: ["entries", tenantId],
    queryFn: () => tenantApi.entries(tenantId),
  });
  const offices = useQuery({
    queryKey: ["offices", tenantId],
    queryFn: () => tenantApi.offices(tenantId),
  });

  const create = useMutation({
    mutationFn: async () => {
      if (!user?.csrf_token) throw new Error("Missing CSRF");
      const oid = officeId || offices.data?.[0]?.id;
      if (!oid) throw new Error("No office");
      return tenantApi.createEntry(tenantId, user.csrf_token, {
        office_id: oid,
        category,
        subcategory,
        answer_text: answer.startsWith("DEMONSTRATION")
          ? answer
          : `DEMONSTRATION ONLY: ${answer}`,
        question_raw: question || undefined,
        verbatim_only: true,
      });
    },
    onSuccess: async () => {
      setShowForm(false);
      setSubcategory("");
      setAnswer("");
      setQuestion("");
      await qc.invalidateQueries({ queryKey: ["entries", tenantId] });
    },
  });

  return (
    <div>
      <PageHeader
        title={m.answers.title}
        actions={
          <Button onClick={() => setShowForm((v) => !v)}>{m.answers.create}</Button>
        }
      />
      {showForm && (
        <Panel className="mb-6 space-y-3">
          <label className="block text-sm">
            {m.answers.office}
            <select
              className="mt-1 w-full border border-ink/15 bg-white px-3 py-2"
              value={officeId}
              onChange={(e) => setOfficeId(e.target.value)}
            >
              <option value="">—</option>
              {(offices.data || []).map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name}
                </option>
              ))}
            </select>
          </label>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block text-sm">
              {m.answers.category}
              <input
                className="mt-1 w-full border border-ink/15 px-3 py-2"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
              />
            </label>
            <label className="block text-sm">
              {m.answers.subcategory}
              <input
                className="mt-1 w-full border border-ink/15 px-3 py-2"
                value={subcategory}
                onChange={(e) => setSubcategory(e.target.value)}
              />
            </label>
          </div>
          <label className="block text-sm">
            {m.answers.question}
            <input
              className="mt-1 w-full border border-ink/15 px-3 py-2"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
            />
          </label>
          <label className="block text-sm">
            {m.answers.answer}
            <textarea
              className="mt-1 w-full border border-ink/15 px-3 py-2"
              rows={4}
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
            />
          </label>
          {create.error && (
            <p className="text-sm text-red-700">{(create.error as Error).message}</p>
          )}
          <Button onClick={() => create.mutate()} disabled={create.isPending || !answer}>
            {m.save}
          </Button>
        </Panel>
      )}
      {entries.isLoading && <p className="text-sm text-[var(--muted)]">{m.loading}</p>}
      {!entries.isLoading && (entries.data?.length || 0) === 0 && <Empty>{m.empty}</Empty>}
      <ul className="divide-y divide-ink/10 border-t border-ink/10">
        {(entries.data || []).map((e) => (
          <li key={e.id} className="flex flex-wrap items-center justify-between gap-3 py-4">
            <div>
              <p className="font-medium">
                {e.category} / {e.subcategory}
              </p>
              <p className="text-sm text-[var(--muted)]">{e.id.slice(0, 8)}…</p>
            </div>
            <span className="text-xs uppercase tracking-wide text-[var(--muted)]">
              {e.verbatim_only ? "verbatim" : "compose"}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
