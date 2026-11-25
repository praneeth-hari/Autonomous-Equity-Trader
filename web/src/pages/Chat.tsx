import { useMutation, useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { SendHorizontal } from 'lucide-react'
import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { Card, PageHeader, Pill } from '../components/ui'
import { api, type ChatTurn } from '../lib/api'

interface Message extends ChatTurn {
  failed?: boolean
}

const SUGGESTIONS = [
  'How is my portfolio doing?',
  'Why did the model skip buying today?',
  'Is the market healthy right now?',
  'Explain my stop-loss in simple words.',
]

export function Chat() {
  const status = useQuery({ queryKey: ['chat-status'], queryFn: api.chatStatus, refetchInterval: 15_000 })
  const [messages, setMessages] = useState<Message[]>([])
  const [draft, setDraft] = useState('')
  const [formError, setFormError] = useState('')
  const endRef = useRef<HTMLDivElement>(null)

  const ask = useMutation({
    mutationFn: ({ text, history }: { text: string; history: ChatTurn[] }) => api.chat(text, history),
    onSuccess: (res) => setMessages((m) => [...m, { role: 'assistant', content: res.reply, failed: !res.ok }]),
    onError: (err: Error) =>
      setMessages((m) => [...m, { role: 'assistant', content: `Couldn't reach the API: ${err.message}`, failed: true }]),
  })

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, ask.isPending])

  const send = (raw: string) => {
    const text = raw.trim()
    if (!text) {
      setFormError('Type a question first.')
      return
    }
    if (ask.isPending) return
    setFormError('')
    const history = messages.filter((m) => !m.failed).map(({ role, content }) => ({ role, content }))
    setMessages((m) => [...m, { role: 'user', content: text }])
    setDraft('')
    ask.mutate({ text, history })
  }

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send(draft)
    }
  }

  const running = status.data?.available
  return (
    <>
      <PageHeader
        eyebrow="Chatbot"
        title="Ask about your portfolio"
        right={
          <Pill tone={status.isLoading ? 'neutral' : running ? 'ok' : 'warn'}>
            {status.isLoading ? 'Checking local AI' : running ? 'Local AI running' : 'Local AI not running'}
          </Pill>
        }
      />

      {!status.isLoading && !running && (
        <Card className="mb-4 border-amber-200 bg-amber-50/60">
          <div className="text-sm font-medium text-amber">Ollama isn't answering</div>
          <p className="mt-1 text-sm text-muted">
            Start the Ollama app, then ask again. The first answer can take a minute while{' '}
            <code className="num">{status.data?.model ?? 'the model'}</code> loads into memory, so close heavy apps if it keeps failing.
          </p>
        </Card>
      )}

      <Card className="flex h-[60vh] flex-col p-0">
        <div className="flex-1 space-y-4 overflow-y-auto p-5" aria-live="polite">
          {messages.length === 0 ? (
            <div className="py-6 text-center">
              <div className="font-medium">Ask anything about your paper account</div>
              <p className="mx-auto mt-1 max-w-md text-sm text-muted">
                Answers use your live portfolio, trades and today's rankings, and run on your own computer. Nothing is sent online.
              </p>
              <div className="mt-4 flex flex-wrap justify-center gap-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => send(s)}
                    className="cursor-pointer rounded-full border border-line px-3 py-1.5 text-sm text-slate-600 transition-colors hover:bg-slate-50"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((m, i) => (
              <div key={i} className={clsx('flex', m.role === 'user' ? 'justify-end' : 'justify-start')}>
                <div
                  className={clsx(
                    'max-w-[80%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm leading-relaxed',
                    m.role === 'user' ? 'bg-brand text-white' : m.failed ? 'border border-red-200 bg-red-50 text-loss' : 'bg-slate-100',
                  )}
                >
                  {m.content}
                </div>
              </div>
            ))
          )}
          {ask.isPending && (
            <div className="flex justify-start" role="status" aria-label="The model is thinking">
              <div className="rounded-2xl bg-slate-100 px-4 py-2.5 text-sm text-muted">Thinking…</div>
            </div>
          )}
          <div ref={endRef} />
        </div>

        <div className="border-t border-line p-3">
          <div className="flex items-end gap-2">
            <textarea
              value={draft}
              onChange={(e) => {
                setDraft(e.target.value)
                if (formError) setFormError('')
              }}
              onKeyDown={onKey}
              rows={2}
              maxLength={2000}
              placeholder="Ask about your portfolio, trades or the rules"
              aria-label="Your question"
              className="flex-1 resize-none rounded-xl border border-line px-3 py-2 text-sm"
            />
            <button
              onClick={() => send(draft)}
              aria-label="Send question"
              className="flex size-10 cursor-pointer items-center justify-center rounded-xl bg-brand text-white transition-opacity hover:opacity-90"
            >
              <SendHorizontal size={18} />
            </button>
          </div>
          {formError && <p className="mt-1.5 text-xs text-loss">{formError}</p>}
          <p className="mt-2 text-xs text-faint">
            Paper trading only. The AI can be wrong and gives no financial advice. Enter sends, Shift+Enter adds a line.
          </p>
        </div>
      </Card>
    </>
  )
}
