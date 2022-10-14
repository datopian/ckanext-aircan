
this.ckan.module('aircan-js', function (jQuery) {
    return {
      options: {
        appendOrUpdate: 'select[name="datastore_append_or_update"]',
      },
      initialize: function () {
        $(this.options.appendOrUpdate).change(function () {
           if(this.value == 'False'){
            $('select[name="datastore_unique_keys"]').prop( "disabled", true );
           } else{
            $('select[name="datastore_unique_keys"]').prop( "disabled", false );
           }
        });
      },
    }
  })