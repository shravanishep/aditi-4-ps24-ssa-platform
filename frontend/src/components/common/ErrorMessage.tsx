export default function ErrorMessage({ message }: { message: string }) {
  return (
    <div className="rounded-md bg-red-950 border border-red-800 p-4 text-red-300 text-sm">
      <span className="font-semibold">Error: </span>
      {message}
    </div>
  )
}
