export default function EmptyState({ title, description, icon: Icon }) {
  return (
    <div className="flex flex-col items-center justify-center h-64 text-center">
      {Icon && (
        <div className="w-12 h-12 rounded-full bg-zinc-800 flex items-center justify-center mb-4">
          <Icon className="text-zinc-500" size={20} />
        </div>
      )}
      <p className="text-sm text-zinc-400">{title}</p>
      {description && (
        <p className="text-xs text-zinc-600 mt-1 max-w-sm">{description}</p>
      )}
    </div>
  )
}
