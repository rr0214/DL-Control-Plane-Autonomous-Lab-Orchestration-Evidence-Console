// App-wide switches. Change a value here; nothing else needs editing.

// The prototype banner at the very top of every screen (including the password screen). Set to false to hide it.
export const SHOW_PROTOTYPE_BANNER = true;

// The example scientist named in decision history lines. Example data: not a real account.
export const EXAMPLE_SCIENTIST = "R. Riggs";

// Where the theme choice is saved in the browser (localStorage). Lives here, not in the theme switch, because the
// server-rendered layout also needs it and cannot import a value from a client component.
export const THEME_KEY = "sdl-theme";

// The role the scientist screens act as when they call the API (role checks happen on the server).
export const SCIENTIST_ROLE = "Scientist (PI)";
