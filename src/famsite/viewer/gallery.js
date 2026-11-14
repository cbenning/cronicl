(function (root) {
  'use strict';
  var api = {};
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  } else {
    root.famsiteGallery = api;
  }
})(typeof window !== 'undefined' ? window : this);
