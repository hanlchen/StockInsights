import SearchBar from "@/components/SearchBar";

export default function SearchPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Search</h1>
      <SearchBar autoFocus />
      <p className="text-sm text-neutral-500">
        Search by ticker or company name across the full NYSE + NASDAQ universe, then select a
        result to view its detail page.
      </p>
    </div>
  );
}
