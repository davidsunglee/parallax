# Processing instants come from the Parallax clock strategy

The TypeScript API obtains temporal processing instants from a clock strategy configured when the `Parallax` handle is created, not from transaction or operation options. This keeps production code from casually overriding audit history while still letting tests inject fixed or controllable clocks.
