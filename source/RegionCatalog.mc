import Toybox.Lang;

// Named places the user can jump the map to via the Regions menu. Selecting one
// recenters the map there (works offline for bundled data); when a tile server
// is configured it also prefetches that area into Application.Storage.
//
// These all fall within the bundled Santa Barbara -> Malibu corridor. Add
// entries outside the bundle to drive on-demand downloads once a server is set.
module RegionCatalog {
    var REGIONS = [
        { :name => "Santa Barbara", :lat => 34.4200, :lon => -119.7000 },
        { :name => "Carpinteria",   :lat => 34.3990, :lon => -119.5190 },
        { :name => "Ventura",       :lat => 34.2750, :lon => -119.2900 },
        { :name => "Oxnard",        :lat => 34.1980, :lon => -119.1790 },
        { :name => "Point Mugu",    :lat => 34.0850, :lon => -119.0600 },
        { :name => "Malibu",        :lat => 34.0360, :lon => -118.6890 }
    ];
}
