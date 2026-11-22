// App-wide switches. Change a value here; nothing else needs editing.

// The prototype banner at the very top of every screen (including the password screen). Set to false to hide it.
export const SHOW_PROTOTYPE_BANNER = true;

// The example scientist named in decision history lines. Example data: not a real account.
export const EXAMPLE_SCIENTIST = "R. Riggs";

// Where the theme choice is saved in the browser (localStorage). Lives here, not in the theme switch, because the
// server-rendered layout also needs it and cannot import a value from a client component.
export const THEME_KEY = "sdl-theme";

// The header's "Phoenix traces" link. One setting, read when the console is built: NEXT_PUBLIC_PHOENIX_URL, the full
// address of the Phoenix project that receives the pipeline's traces (project sdl-control-plane), for example
// http://localhost:6006/projects/UHJvamVjdDoz locally. The project ID comes from Phoenix's own database, so recheck it
// after any Phoenix reset or redeploy. Unset or empty: the link goes to the Traces section of the Architecture page.
export const PHOENIX_TRACES_URL = (process.env.NEXT_PUBLIC_PHOENIX_URL ?? "").trim();
export const TRACES_SECTION = "/architecture#traces";
export const PHOENIX_TRACES_NOTE = "Read-only login, ask for access";

// The role the scientist screens act as when they call the API (role checks happen on the server).
export const SCIENTIST_ROLE = "Scientist (PI)";
