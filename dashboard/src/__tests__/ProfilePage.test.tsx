import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '../api';
import { ApiError } from '../api';
import ProfilePage from '../pages/ProfilePage';
import type { ProfileDocs, ProfileFields, ProfileResponse } from '../types';

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return { ...actual, getProfile: vi.fn(), saveProfile: vi.fn(), syncProfileDocs: vi.fn() };
});

// Synthetic profile, no real person.
const FIELDS: ProfileFields = {
  first_name: 'Ada', last_name: '', phone: '555-000-0000', email: '', linkedin_url: '', github_url: '',
  location: '', current_job_title: '', years_experience: null, education_level: null, skills: [],
};
const RESPONSE: ProfileResponse = {
  profile: FIELDS, has_resume: false, resume_file_name: null, content_library_md: '',
  content_library_error: null, profile_docs: null,
  options: { education_level: ['high_school', 'bachelors', 'masters', 'phd'] },
};
const minutesAgo = (n: number) => new Date(Date.now() - n * 60000).toISOString();
const DOCS: ProfileDocs = {
  library: { url: 'https://docs.google.com/document/d/L/edit', synced_at: minutesAgo(5) },
  resume: { url: 'https://docs.google.com/document/d/R/edit', synced_at: minutesAgo(5) },
  about: { url: 'https://docs.google.com/document/d/A/edit', synced_at: minutesAgo(5) },
};

function renderPage() {
  render(<MemoryRouter><ProfilePage /></MemoryRouter>);
  return userEvent.setup();
}

beforeEach(() => {
  vi.mocked(api.getProfile).mockResolvedValue(structuredClone(RESPONSE));
  vi.mocked(api.saveProfile).mockImplementation(async (profile) => ({ ...RESPONSE, profile }));
});

describe('ProfilePage', () => {
  it('shows the saved profile and the header line', async () => {
    renderPage();
    expect(await screen.findByLabelText('First name')).toHaveValue('Ada');
    expect(screen.getByLabelText('Phone')).toHaveValue('555-000-0000');
    expect(screen.getByText(/Profile is about you;/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
  });

  it('has no content library box and no resume upload', async () => {
    renderPage();
    await screen.findByLabelText('First name');
    expect(screen.queryByLabelText('Content library')).toBeNull();
    expect(screen.queryByLabelText('Upload resume')).toBeNull();
    expect(screen.queryByRole('textbox', { name: /library/i })).toBeNull();
  });

  it('saves edited fields', async () => {
    const user = renderPage();
    const phone = await screen.findByLabelText('Phone');
    await user.clear(phone);
    await user.type(phone, '555-111-2222');
    await user.type(screen.getByLabelText('Skills'), 'Python{Enter}');
    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(api.saveProfile).toHaveBeenCalledWith({ ...FIELDS, phone: '555-111-2222', skills: ['Python'] });
    expect(await screen.findByText('Saved.')).toBeInTheDocument();
  });

  it('discard puts the saved values back', async () => {
    const user = renderPage();
    await user.type(await screen.findByLabelText('Last name'), 'Typed');
    await user.click(screen.getByRole('button', { name: 'Discard' }));
    expect(screen.getByLabelText('Last name')).toHaveValue('');
  });

  it('points to the Claude setup page before the Profile Docs are set up', async () => {
    renderPage();
    expect(await screen.findByText(/aren't in Google Docs yet/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Claude setup page' })).toHaveAttribute('href', '/claude-setup');
    expect(screen.queryByRole('button', { name: 'Sync now' })).toBeNull();
  });

  it('links the Profile Docs with when they were last synced', async () => {
    vi.mocked(api.getProfile).mockResolvedValue({ ...RESPONSE, profile_docs: DOCS });
    renderPage();
    const docs = await screen.findByRole('list', { name: 'Profile Docs' });
    expect(within(docs).getByRole('link', { name: /Content Library/ })).toHaveAttribute('href', DOCS.library!.url);
    expect(within(docs).getByRole('link', { name: /Base Resume/ })).toHaveAttribute('href', DOCS.resume!.url);
    expect(within(docs).getByRole('link', { name: /About me/ })).toHaveAttribute('href', DOCS.about!.url);
    expect(screen.getByText(/Last synced 5 minutes ago/)).toBeInTheDocument();
  });

  it('syncs now', async () => {
    vi.mocked(api.getProfile).mockResolvedValue({ ...RESPONSE, profile_docs: DOCS });
    const synced = { library: { ...DOCS.library!, synced_at: minutesAgo(0) }, resume: { ...DOCS.resume!, synced_at: minutesAgo(0) },
      about: { ...DOCS.about!, synced_at: minutesAgo(0) } };
    vi.mocked(api.syncProfileDocs).mockResolvedValue({
      ...RESPONSE, profile_docs: synced, ok: true, problems: [], warnings: [], changed: true, draft: {}, parse_error: null,
    });
    const user = renderPage();
    await user.click(await screen.findByRole('button', { name: 'Sync now' }));
    expect(api.syncProfileDocs).toHaveBeenCalled();
    expect(await screen.findByText(/Last synced just now/)).toBeInTheDocument();
    expect(screen.getByText('Synced: your changes are in.')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('shows About me warnings after a sync that saved', async () => {
    vi.mocked(api.getProfile).mockResolvedValue({ ...RESPONSE, profile_docs: DOCS });
    vi.mocked(api.syncProfileDocs).mockResolvedValue({
      ...RESPONSE, profile_docs: DOCS, ok: true, problems: [], changed: false, draft: {}, parse_error: null,
      warnings: ['The About me Doc has no answers yet: Claude needs them for your cover letters.'],
    });
    const user = renderPage();
    await user.click(await screen.findByRole('button', { name: 'Sync now' }));
    expect(await screen.findByText(/About me Doc has no answers yet/)).toBeInTheDocument();
    expect(screen.getByText('Synced: nothing changed.')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('lists the problems a sync found', async () => {
    vi.mocked(api.getProfile).mockResolvedValue({ ...RESPONSE, profile_docs: DOCS });
    vi.mocked(api.syncProfileDocs).mockResolvedValue({
      ...RESPONSE, profile_docs: DOCS, ok: false, warnings: [], changed: false, draft: {}, parse_error: null,
      problems: ['The Content Library Doc has no projects.'],
    });
    const user = renderPage();
    await user.click(await screen.findByRole('button', { name: 'Sync now' }));
    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText('The Content Library Doc has no projects.')).toBeInTheDocument();
    expect(alert).toHaveTextContent('Nothing was synced');
  });

  it('fills the empty fields from the resume, highlighted, without saving them until Save', async () => {
    vi.mocked(api.getProfile).mockResolvedValue({ ...RESPONSE, profile_docs: DOCS });
    vi.mocked(api.syncProfileDocs).mockResolvedValue({
      ...RESPONSE, profile_docs: DOCS, ok: true, problems: [], warnings: [], changed: true, parse_error: null,
      draft: { last_name: 'Example', current_job_title: 'Widget Engineer', education_level: 'masters',
        years_experience: 4, skills: ['Python', 'SQL'] },
    });
    const user = renderPage();
    await user.click(await screen.findByRole('button', { name: 'Sync now' }));
    expect(await screen.findByLabelText('Last name')).toHaveValue('Example');
    expect(screen.getByLabelText('Current title')).toHaveValue('Widget Engineer');
    expect(screen.getByLabelText('Education')).toHaveValue('masters');
    expect(screen.getByLabelText('Years of experience')).toHaveValue(4);
    expect(screen.getByText('SQL')).toBeInTheDocument();
    expect(screen.getByLabelText('First name')).toHaveValue('Ada');
    expect(screen.getAllByText('From resume')).toHaveLength(5);
    expect(screen.getByLabelText('Last name').closest('.pref-row')).toHaveClass('drafted');
    expect(screen.getByText(/The highlighted fields are from your resume/)).toBeInTheDocument();
    expect(api.saveProfile).not.toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: 'Save' }));
    expect(api.saveProfile).toHaveBeenCalledWith(expect.objectContaining({
      first_name: 'Ada', last_name: 'Example', current_job_title: 'Widget Engineer', education_level: 'masters',
      years_experience: 4, skills: ['Python', 'SQL'],
    }));
    await waitFor(() => expect(screen.queryAllByText('From resume')).toHaveLength(0));
  });

  it('a field typed before the sync keeps the typed value, and Discard drops the draft', async () => {
    vi.mocked(api.getProfile).mockResolvedValue({ ...RESPONSE, profile_docs: DOCS });
    vi.mocked(api.syncProfileDocs).mockResolvedValue({
      ...RESPONSE, profile_docs: DOCS, ok: true, problems: [], warnings: [], changed: false, parse_error: null,
      draft: { last_name: 'Example', location: 'Springfield' },
    });
    const user = renderPage();
    await user.type(await screen.findByLabelText('Last name'), 'Typed');
    await user.click(screen.getByRole('button', { name: 'Sync now' }));
    expect(await screen.findByLabelText('Location')).toHaveValue('Springfield');
    expect(screen.getAllByText('From resume')).toHaveLength(1);
    expect(screen.getByLabelText('Last name')).toHaveValue('Typed');
    await user.click(screen.getByRole('button', { name: 'Discard' }));
    expect(screen.getByLabelText('Location')).toHaveValue('');
    expect(screen.queryAllByText('From resume')).toHaveLength(0);
  });

  it('shows why the resume could not be read after a good sync', async () => {
    vi.mocked(api.getProfile).mockResolvedValue({ ...RESPONSE, profile_docs: DOCS });
    vi.mocked(api.syncProfileDocs).mockResolvedValue({
      ...RESPONSE, profile_docs: DOCS, ok: true, problems: [], warnings: [], changed: true, draft: {},
      parse_error: 'Synced, but your resume couldn\'t be read to fill in your profile (ValueError).',
    });
    const user = renderPage();
    await user.click(await screen.findByRole('button', { name: 'Sync now' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn't be read to fill in your profile/);
    expect(screen.getByText('Synced: your changes are in.')).toBeInTheDocument();
  });

  it('shows a sync error', async () => {
    vi.mocked(api.getProfile).mockResolvedValue({ ...RESPONSE, profile_docs: DOCS });
    vi.mocked(api.syncProfileDocs).mockRejectedValue(new ApiError(409, 'Connect Google Drive on the Claude setup page'));
    const user = renderPage();
    await user.click(await screen.findByRole('button', { name: 'Sync now' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Connect Google Drive on the Claude setup page');
  });
});
