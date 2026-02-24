export function ReleaseTable() {
  return (
    <section className="rounded-xl border border-white/10 bg-white/5 p-4">
      <h2 className="mb-2 text-lg font-semibold">Releases</h2>
      <div className="overflow-x-auto">
        <table className="table-enterprise density-cozy">
          <thead>
            <tr>
              <th>Provider</th>
              <th>Protocol</th>
              <th>Size</th>
              <th>Seeders</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Indexer A</td>
              <td>torrent</td>
              <td>2.4 GB</td>
              <td>114</td>
              <td>
                <button className="btn-primary">Send to RD</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  );
}
