import type { Mock } from 'vitest';
import { RemoteWorkspace } from '../index';
import { FileClient } from '../client/file-client';

const originalFetch = global.fetch;

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

describe('RemoteWorkspace git query parameters', () => {
  it('discovers repositories and files with native Windows paths', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ repositories: [{ path: 'repo' }], truncated: false }))
      .mockResolvedValueOnce(jsonResponse({ files: ['repo/file.txt'], truncated: true }))
      .mockResolvedValueOnce(jsonResponse([]));
    global.fetch = fetchMock as typeof fetch;
    const ws = new RemoteWorkspace({ host: 'http://example.com', workingDir: 'C:\\work' });
    expect(await ws.gitRepositories('C:\\work')).toEqual({
      repositories: [{ path: 'repo' }],
      truncated: false,
    });
    expect(await new FileClient({ host: 'http://example.com' }).listFiles('C:\\work', 1)).toEqual({
      files: ['repo/file.txt'],
      truncated: true,
    });
    await ws.gitChanges('C:\\work\\repo', { includeNested: false });
    expect(new URL(fetchMock.mock.calls[0][0] as string).searchParams.get('path')).toBe('C:\\work');
    expect(new URL(fetchMock.mock.calls[1][0] as string).searchParams.get('limit')).toBe('1');
    expect(new URL(fetchMock.mock.calls[2][0] as string).searchParams.get('include_nested')).toBe(
      'false'
    );
  });
  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('omits ref by default for gitChanges', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([])) as Mock;
    global.fetch = fetchMock as typeof fetch;

    const ws = new RemoteWorkspace({ host: 'http://example.com', workingDir: '/tmp' });
    await ws.gitChanges('/repo');

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const url = new URL(fetchMock.mock.calls[0][0] as string);
    expect(url.pathname).toBe('/api/git/changes');
    expect(url.searchParams.get('path')).toBe('/repo');
    expect(url.searchParams.has('ref')).toBe(false);
  });

  it('forwards ref to gitChanges as a query param', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([])) as Mock;
    global.fetch = fetchMock as typeof fetch;

    const ws = new RemoteWorkspace({ host: 'http://example.com', workingDir: '/tmp' });
    await ws.gitChanges('/repo', { ref: 'HEAD' });

    const url = new URL(fetchMock.mock.calls[0][0] as string);
    expect(url.pathname).toBe('/api/git/changes');
    expect(url.searchParams.get('path')).toBe('/repo');
    expect(url.searchParams.get('ref')).toBe('HEAD');
  });

  it('omits ref by default for gitDiff', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ original: '', modified: '' })) as Mock;
    global.fetch = fetchMock as typeof fetch;

    const ws = new RemoteWorkspace({ host: 'http://example.com', workingDir: '/tmp' });
    await ws.gitDiff('/repo/file.ts');

    const url = new URL(fetchMock.mock.calls[0][0] as string);
    expect(url.pathname).toBe('/api/git/diff');
    expect(url.searchParams.get('path')).toBe('/repo/file.ts');
    expect(url.searchParams.has('ref')).toBe(false);
  });

  it('forwards ref to gitDiff as a query param', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ original: '', modified: '' })) as Mock;
    global.fetch = fetchMock as typeof fetch;

    const ws = new RemoteWorkspace({ host: 'http://example.com', workingDir: '/tmp' });
    await ws.gitDiff('/repo/file.ts', { ref: 'abc1234' });

    const url = new URL(fetchMock.mock.calls[0][0] as string);
    expect(url.pathname).toBe('/api/git/diff');
    expect(url.searchParams.get('path')).toBe('/repo/file.ts');
    expect(url.searchParams.get('ref')).toBe('abc1234');
  });
});
