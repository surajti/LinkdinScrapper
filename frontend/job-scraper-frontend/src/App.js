import React, { useState } from 'react';
import axios from 'axios';
import './index.css';

const API_URL = 'http://localhost:8000/api';

function App() {
  const [role, setRole] = useState('');
  const [location, setLocation] = useState('');
  const [limit, setLimit] = useState(20);
  const [postedWithin, setPostedWithin] = useState(60); // minutes
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [jobs, setJobs] = useState(null);
  const [doneJobs, setDoneJobs] = useState([]);
  const [activeTab, setActiveTab] = useState('search');
  const [dbDoneJobs, setDbDoneJobs] = useState([]);
  const [loadingDone, setLoadingDone] = useState(false);
  const [viewMode, setViewMode] = useState('grid'); // 'grid' | 'single'

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setJobs(null);

    try {
      const { data } = await axios.post(`${API_URL}/search`, {
        role,
        location,
        limit: Number(limit),
        posted_within_minutes: Number(postedWithin),
      });
      setJobs(data);
    } catch (err) {
      setError('Failed to fetch jobs. Make sure the backend is running on port 8000.');
    } finally {
      setLoading(false);
    }
  };

  const handleNewSearch = () => {
    setJobs(null);
    setError(null);
    setViewMode('grid');
  };

  const handleDone = async (job) => {
    // Remove from current jobs
    setJobs((prevJobs) => prevJobs.filter((j) => j.url !== job.url));
    // Add to done list
    setDoneJobs((prevDone) => [...prevDone, job]);

    // Save to backend tracking table
    try {
      await axios.post(`${API_URL}/done`, job);
    } catch (e) {
      console.error("Failed to mark as done", e);
    }
  };

  const handleViewJob = (e, job) => {
    e.preventDefault();
    window.open(job.url, '_blank', 'noopener,noreferrer');
    handleDone(job);
  };

  const handleDelete = async (job) => {
    // Remove from current jobs
    setJobs((prevJobs) => prevJobs.filter((j) => j.url !== job.url));

    // Save to backend deleted table
    try {
      await axios.post(`${API_URL}/delete`, job);
    } catch (e) {
      console.error("Failed to mark as deleted", e);
    }
  };

  const fetchDoneJobs = async () => {
    setLoadingDone(true);
    try {
      const { data } = await axios.get(`${API_URL}/done`);
      setDbDoneJobs(data);
    } catch (err) {
      console.error("Failed to fetch done jobs", err);
    } finally {
      setLoadingDone(false);
    }
  };

  const handleTabChange = (tab) => {
    setActiveTab(tab);
    if (tab === 'done') {
      fetchDoneJobs();
    }
  };

  return (
    <div className="container">
      <header className="header">
        <h1>Keka <span style={{ fontWeight: 400, opacity: 0.75 }}>(keka)</span></h1>
      </header>

      {/* ── Tabs ── */}
      <div className="tabs">
        <button
          className={`tab-btn ${activeTab === 'search' ? 'active' : ''}`}
          onClick={() => handleTabChange('search')}
        >
          Search
        </button>
        <button
          className={`tab-btn ${activeTab === 'done' ? 'active' : ''}`}
          onClick={() => handleTabChange('done')}
        >
          Done
        </button>
      </div>

      {/* ── Search Tab ── */}
      {activeTab === 'search' && (
        <>
          {/* ── Search form ── */}
          {jobs === null && (
            <div className="dashboard" style={{ maxWidth: '700px', margin: '0 auto' }}>
              <aside className="sidebar">
                <div className="glass-panel">
                  <h2>Search Jobs</h2>
                  <form onSubmit={handleSubmit}>
                    <div className="form-group">
                      <label>Job Role</label>
                      <input
                        id="role-input"
                        type="text"
                        className="form-control"
                        value={role}
                        onChange={(e) => setRole(e.target.value)}
                        placeholder="e.g. Software Engineer"
                        required
                        disabled={loading}
                      />
                    </div>

                    <div className="form-group">
                      <label>Location</label>
                      <input
                        id="location-input"
                        type="text"
                        className="form-control"
                        value={location}
                        onChange={(e) => setLocation(e.target.value)}
                        placeholder="e.g. San Francisco, CA"
                        required
                        disabled={loading}
                      />
                    </div>

                    <div className="form-group">
                      <label>Max Results</label>
                      <input
                        id="limit-input"
                        type="number"
                        className="form-control"
                        value={limit}
                        onChange={(e) => setLimit(e.target.value)}
                        min="5"
                        max="50"
                        required
                        disabled={loading}
                      />
                    </div>

                    <div className="form-group">
                      <label>Posted within (minutes, max 3600)</label>
                      <input
                        id="posted-within-input"
                        type="number"
                        className="form-control"
                        value={postedWithin}
                        onChange={(e) => setPostedWithin(e.target.value)}
                        min="1"
                        max="3600"
                        required
                        disabled={loading}
                      />
                      <small style={{ color: 'var(--text-secondary)', fontSize: '0.8rem' }}>
                        1 = last 1 min &nbsp;·&nbsp; 60 = last hour &nbsp;·&nbsp; 3600 = last 2.5 days
                      </small>
                    </div>

                    <button id="search-btn" type="submit" className="btn-primary" disabled={loading}>
                      {loading
                        ? <><div className="loading-spinner" style={{ display: 'inline-block', marginRight: '0.5rem' }}></div>Searching…</>
                        : 'Search Jobs'}
                    </button>

                    {error && (
                      <div className="status-message status-error" style={{ marginTop: '1rem' }}>
                        {error}
                      </div>
                    )}
                  </form>

                  {loading && (
                    <div style={{ marginTop: '1.5rem', textAlign: 'center', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
                      <div className="loading-spinner-large" style={{ margin: '0 auto 0.75rem' }}></div>
                      Fetching jobs from LinkedIn… this may take 20–40 seconds.
                    </div>
                  )}
                </div>
              </aside>
            </div>
          )}

          {/* ── Results ── */}
          {jobs !== null && (
            <div className="dashboard">
              <main className="main-content">
                <div className="glass-panel" style={{ minHeight: '400px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '10px' }}>
                    <h2>Results ({jobs.length} jobs)</h2>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <div style={{ display: 'flex', background: 'rgba(255,255,255,0.05)', borderRadius: '30px', padding: '4px' }}>
                        <button
                          onClick={() => setViewMode('grid')}
                          className={`tab-btn ${viewMode === 'grid' ? 'active' : ''}`}
                          style={{ padding: '6px 16px', fontSize: '0.85rem', margin: 0, minWidth: '80px' }}>
                          Grid
                        </button>
                        <button
                          onClick={() => setViewMode('single')}
                          className={`tab-btn ${viewMode === 'single' ? 'active' : ''}`}
                          style={{ padding: '6px 16px', fontSize: '0.85rem', margin: 0, minWidth: '80px' }}>
                          Swipe
                        </button>
                      </div>
                      <button id="new-search-btn" onClick={handleNewSearch} className="btn-primary" style={{ padding: '0.5rem 1.25rem' }}>
                        ← New Search
                      </button>
                    </div>
                  </div>

                  {jobs.length === 0 ? (
                    <div className="empty-state">
                      <p>No jobs found. Try different keywords or a broader location.</p>
                    </div>
                  ) : viewMode === 'grid' ? (
                    <div className="jobs-grid">
                      {jobs.map((job, i) => (
                        <div key={i} className="job-card">
                          <h3 className="job-title">{job.title}</h3>
                          <p className="job-company">{job.company}</p>
                          <p className="job-location" style={{ marginBottom: '0.5rem' }}>📍 {job.location}</p>
                          <div style={{ display: 'flex', gap: '10px', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
                            {job.followers > 0 && (
                              <span style={{ color: '#a855f7', fontSize: '0.85rem', fontWeight: '500' }}>
                                {job.followers.toLocaleString()} followers
                              </span>
                            )}
                            {job.experience_years >= 2 && (
                              <span style={{ color: '#f59e0b', fontSize: '0.85rem', fontWeight: '500' }}>
                                {job.experience_years}+ years exp
                              </span>
                            )}
                          </div>
                          <div className="job-footer">
                            <button onClick={() => handleDelete(job)} className="btn-link btn-delete">
                              ✕ Pass
                            </button>
                            <button onClick={() => handleDone(job)} className="btn-link btn-done">
                              ✓ Done
                            </button>
                            <a href={job.url} className="btn-link" onClick={(e) => handleViewJob(e, job)}>
                              View Job →
                            </a>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="single-view-container" style={{ display: 'flex', justifyContent: 'center', padding: '20px 0' }}>
                      <div className="job-card single-card" style={{ width: '100%', maxWidth: '600px', transform: 'none', padding: '40px' }}>
                        <h3 className="job-title" style={{ fontSize: '1.8rem', marginBottom: '1rem' }}>{jobs[0].title}</h3>
                        <p className="job-company" style={{ fontSize: '1.1rem', marginBottom: '0.5rem', color: '#60a5fa' }}>{jobs[0].company}</p>
                        <p className="job-location" style={{ fontSize: '1rem', color: '#94a3b8', marginBottom: '0.5rem' }}>📍 {jobs[0].location}</p>
                        <div style={{ display: 'flex', gap: '15px', marginBottom: '2rem', flexWrap: 'wrap' }}>
                          {jobs[0].followers > 0 && (
                            <span style={{ color: '#a855f7', fontSize: '1.1rem', fontWeight: '500' }}>
                              {jobs[0].followers.toLocaleString()} followers
                            </span>
                          )}
                          {jobs[0].experience_years >= 2 && (
                            <span style={{ color: '#f59e0b', fontSize: '1.1rem', fontWeight: '500' }}>
                              {jobs[0].experience_years}+ years exp
                            </span>
                          )}
                        </div>
                        <p style={{ marginBottom: '2rem' }}>
                          <a href={jobs[0].url} className="btn-link" style={{ padding: '10px 20px', fontSize: '1rem' }} onClick={(e) => handleViewJob(e, jobs[0])}>
                            Read Full Post on LinkedIn →
                          </a>
                        </p>

                        <div className="job-footer" style={{ display: 'flex', gap: '15px', justifyContent: 'center', paddingTop: '20px' }}>
                          <button onClick={() => handleDelete(jobs[0])} className="btn-link btn-delete" style={{ padding: '12px 30px', fontSize: '1.1rem' }}>
                            ✕ Pass
                          </button>
                          <button onClick={() => handleDone(jobs[0])} className="btn-link btn-done" style={{ padding: '12px 30px', fontSize: '1.1rem' }}>
                            ✓ Done
                          </button>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* DONE JOBS SECTION */}
                  {doneJobs.length > 0 && (
                    <div style={{ marginTop: '3rem' }}>
                      <h3 style={{ color: '#10b981', marginBottom: '1rem', paddingBottom: '0.5rem', borderBottom: '1px solid rgba(16, 185, 129, 0.2)' }}>
                        ✓ Done ({doneJobs.length})
                      </h3>
                      <div className="jobs-grid">
                        {doneJobs.map((job, i) => (
                          <div key={i} className="job-card" style={{ opacity: 0.6 }}>
                            <h3 className="job-title" style={{ fontSize: '1rem' }}>{job.title}</h3>
                            <p className="job-company" style={{ fontSize: '0.85rem' }}>{job.company}</p>
                            <div className="job-footer" style={{ paddingTop: '10px' }}>
                              <a href={job.url} target="_blank" rel="noopener noreferrer" className="btn-link" style={{ fontSize: '0.8rem', padding: '4px 8px' }}>
                                View Job →
                              </a>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </main>
            </div>
          )}
        </>
      )}

      {/* ── Done Tab ── */}
      {activeTab === 'done' && (
        <div className="dashboard">
          <main className="main-content">
            <div className="glass-panel" style={{ minHeight: '400px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                <h2>Done Jobs ({dbDoneJobs.length})</h2>
                <button onClick={fetchDoneJobs} className="btn-primary" style={{ padding: '0.5rem 1.25rem', width: 'auto' }}>
                  Refresh
                </button>
              </div>

              {loadingDone ? (
                <div style={{ textAlign: 'center', padding: '2rem' }}>
                  <div className="loading-spinner-large" style={{ margin: '0 auto 1rem' }}></div>
                  <p>Loading...</p>
                </div>
              ) : dbDoneJobs.length === 0 ? (
                <div className="empty-state">
                  <p>No jobs marked as done yet.</p>
                </div>
              ) : (
                <div className="jobs-grid">
                  {dbDoneJobs.map((job, i) => (
                    <div key={i} className="job-card">
                      <h3 className="job-title">{job.title}</h3>
                      <p className="job-company">{job.company}</p>
                      <p className="job-location">📍 {job.location}</p>
                      <div className="job-footer">
                        <span style={{ fontSize: '0.85rem', color: '#10b981' }}>{job.posted_time}</span>
                        <a href={job.url} target="_blank" rel="noopener noreferrer" className="btn-link">
                          View Link →
                        </a>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </main>
        </div>
      )}
    </div>
  );
}

export default App;
