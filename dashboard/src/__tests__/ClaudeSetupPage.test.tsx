import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '../api';
import ClaudeSetupPage from '../pages/ClaudeSetupPage';
import type { ClaudeSetup, ProfileDocs, ProfileResponse } from '../types';

vi.mock('../api');

const DOCS: ProfileDocs = {
  library: { url: 'https://docs.google.com/document/d/L/edit', synced_at: '2026-10-26T09:30:00+00:00' },
  resume: { url: 'https://docs.google.com/document/d/R/edit', synced_at: '2026-10-26T09:30:00+00:00' },
};

function setup(extra: Partial<ClaudeSetup> = {}): ClaudeSetup {
  return {
    drive: true, drive_detail: 'Connected 2026-10-16', drive_source: 'user', connect_url: '/strelitzia/dashboard/api/drive/connect',
    rules_version: 'r1234567',
    instructions_version: 'i7654321',
    profile_docs: null,
    project_name: 'Strelitzia Resumes',
    project_instructions: 'Instructions version: i7654321\n\nYou tailor my resume and cover letter for one job per chat.',
    ...extra,
  };
}

const profile = (docs: ProfileDocs | null): ProfileResponse => ({
  profile: {
    first_name: '', last_name: '', phone: '', email: '', linkedin_url: '', github_url: '', location: '',
    current_job_title: '', years_experience: null, education_level: null, skills: [],
  },
  has_resume: true, resume_file_name: null, content_library_md: '', content_library_error: null,
  profile_docs: docs, options: { education_level: [] },
});

const renderPage = (path = '/claude-setup') => render(
  <MemoryRouter initialEntries={[path]}><ClaudeSetupPage /></MemoryRouter>,
);

beforeEach(() => {
  vi.mocked(api.getClaudeSetup).mockResolvedValue(setup());
});

describe('ClaudeSetupPage', () => {
  it('lists the steps with the instructions version and no rules file', async () => {
    renderPage();
    expect(await screen.findByRole('heading', { name: 'Claude setup' })).toBeInTheDocument();
    expect(screen.getByText('Strelitzia Resumes')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Download rules/ })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Copy rules' })).toBeNull();
    expect(screen.getByText(/Instructions version i7654321 · rules version r1234567/)).toBeInTheDocument();
    expect(screen.getByText(/rules come inside each job's packet/)).toBeInTheDocument();
    expect(screen.getByText(/can only see files it created/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Write the Docs|Refresh the Docs/ })).toBeNull();
  });

  it('copies the project instructions with their version line', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: 'Copy instructions' }));
    expect(api.copyText).toHaveBeenCalledWith('Instructions version: i7654321\n\nYou tailor my resume and cover letter for one job per chat.');
    expect(screen.getByRole('button', { name: 'Copied' })).toBeInTheDocument();
  });

  it('sets up the Profile Docs and links them', async () => {
    const user = userEvent.setup();
    vi.mocked(api.setupProfileDocs).mockResolvedValue({ ok: true, profile: profile(DOCS) });
    renderPage();
    await user.click(await screen.findByRole('button', { name: 'Set up Profile Docs' }));
    expect(api.setupProfileDocs).toHaveBeenCalledWith(false);
    const docs = await screen.findByRole('list', { name: 'Profile Docs' });
    expect(within(docs).getByRole('link', { name: /Content Library/ })).toHaveAttribute('href', DOCS.library!.url);
    expect(within(docs).getByRole('link', { name: /Base Resume/ })).toHaveAttribute('href', DOCS.resume!.url);
  });

  it('asks before overwriting existing Profile Docs, and Cancel changes nothing', async () => {
    const user = userEvent.setup();
    vi.mocked(api.getClaudeSetup).mockResolvedValue(setup({ profile_docs: DOCS }));
    vi.mocked(api.setupProfileDocs).mockResolvedValueOnce({
      ok: false, existing: ['Content Library', 'Base Resume'],
    });
    renderPage();
    await user.click(await screen.findByRole('button', { name: 'Set up Profile Docs' }));
    const dialog = await screen.findByRole('alertdialog');
    expect(dialog).toHaveTextContent('This will overwrite: Content Library, Base Resume. Continue?');
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect(api.setupProfileDocs).toHaveBeenCalledTimes(1);

    vi.mocked(api.setupProfileDocs).mockResolvedValueOnce({
      ok: false, existing: ['Content Library', 'Base Resume'],
    });
    vi.mocked(api.setupProfileDocs).mockResolvedValueOnce({ ok: true, profile: profile(DOCS) });
    await user.click(screen.getByRole('button', { name: 'Set up Profile Docs' }));
    await user.click(within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Overwrite' }));
    expect(api.setupProfileDocs).toHaveBeenLastCalledWith(true);
    expect(await screen.findByRole('button', { name: 'Set up Profile Docs' })).toBeInTheDocument();
    expect(screen.queryByRole('alertdialog')).toBeNull();
  });

  it('needs Drive before the Profile Docs', async () => {
    vi.mocked(api.getClaudeSetup).mockResolvedValue(setup({ drive: false, drive_source: null, drive_detail: 'Not connected' }));
    renderPage();
    expect(await screen.findByText(/Google Drive isn't set up/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Set up Profile Docs' })).toBeDisabled();
  });

  it('offers Connect Google Drive when Drive is not connected', async () => {
    vi.mocked(api.getClaudeSetup).mockResolvedValue(setup({
      drive: false, drive_source: null, drive_detail: 'Connect Google Drive on the Claude setup page',
    }));
    renderPage();
    expect(await screen.findByRole('link', { name: 'Connect Google Drive' })).toHaveAttribute('href', '/strelitzia/dashboard/api/drive/connect');
    expect(screen.queryByRole('button', { name: 'Disconnect' })).not.toBeInTheDocument();
  });

  it('shows the connect outcome and disconnects', async () => {
    const user = userEvent.setup();
    vi.mocked(api.disconnectDrive).mockResolvedValue({ ok: true });
    renderPage('/claude-setup?drive=connected');
    expect(await screen.findByText('Google Drive is connected.')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Connect Google Drive' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Reconnect' })).toHaveAttribute('href', '/strelitzia/dashboard/api/drive/connect');
    expect(screen.getByText('Connected')).toBeInTheDocument();
    vi.mocked(api.getClaudeSetup).mockResolvedValue(setup({ drive: false, drive_source: null }));
    await user.click(screen.getByRole('button', { name: 'Disconnect' }));
    expect(api.disconnectDrive).toHaveBeenCalled();
    expect(await screen.findByRole('link', { name: 'Connect Google Drive' })).toBeInTheDocument();
    expect(screen.queryByText('Google Drive is connected.')).not.toBeInTheDocument();
  });

  it('says why a connect failed', async () => {
    renderPage('/claude-setup?drive=denied');
    expect(await screen.findByText(/wasn't connected: allow access/)).toBeInTheDocument();
  });
});
