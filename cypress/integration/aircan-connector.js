let headers;
const uuid = () => Math.random().toString(36).slice(2) + '_test'
let resource_name = uuid();
let resource_id = null;
describe('Aircan Connector', () => {
  beforeEach(function() {
    cy.clearCookies()
    cy.fixture('aircan.json').as('testData').then(() => {
      cy.login(this.testData.username, this.testData.password)
    })
    cy.fixture('aircan.json').as('testData').then(() => {
      headers = {
        'Authorization': this.testData.apiKey,
        'content-type': 'application/json'
      }
    })
  })

  it('API: Create Resource', () => {
    let body = {

      "package_id": "another-ds",
      "url": "https://gist.githubusercontent.com/hannelita/859e96ca8f60e7c973a2996ae9b6b307/raw/478c3c2f97ccf6d028181ae5dc0678a3783b09ca/r4.csv",
      "description": resource_name,
      "schema": {
        "fields": [{
            "name": "FID",
            "title": "FID",
            "type": "float",
            "description": "FID`"
          },
          {
            "name": "MktRF",
            "title": "MktRF",
            "type": "float",
            "description": "MktRF`"
          },
          {
            "name": "SMB",
            "title": "SMB",
            "type": "float",
            "description": "SMB`"
          },
          {
            "name": "HML",
            "title": "HML",
            "type": "float",
            "description": "HML`"
          },
          {
            "name": "RF",
            "title": "RF",
            "type": "float",
            "description": "RF`"
          }
        ]
      }
    }

    cy.request({
      method: 'POST',
      url: '/api/3/action/resource_create',
      headers: headers,
      body: body
    }).then((resp) => {
      resource_id = resp.body.result.id
      expect(resp.body.success).to.eq(true)
      let resource_url = `/dataset/another-ds/resource/${resource_id}`
      cy.wait(180000)
      cy.visit({
        url: resource_url
      }).then((resp) => {
        cy.get('.module-content > h2 ').contains('Data Dictionary')
      })
    })
  })

  it('API: Validate Data', () => {
    let resource_url = `/api/3/action/datastore_search?resource_id=${resource_id}`;
    let fields = [{
        "type": "int",
        "id": "_id"
      },
      {
        "type": "float8",
        "id": "FID"
      },
      {
        "type": "float8",
        "id": "MktRF"
      },
      {
        "type": "float8",
        "id": "SMB"
      },
      {
        "type": "float8",
        "id": "HML"
      },
      {
        "type": "float8",
        "id": "RF"
      },
      {
        "type": "float8",
        "id": "Mkt-RF"
      }
    ]
    let record = {
      "_id": 1,
      "FID": 192607,
      "MktRF": null,
      "SMB": -2.3,
      "HML": -2.87,
      "RF": 0.22,
      "Mkt-RF": 2.96
    }
    cy.request({
      url: resource_url,
      headers: headers
    }).then((resp) => {
      expect(resp.body.result.fields).to.deep.eq(fields)
      expect(resp.body.result.records_format).to.equal('objects')
      expect(resp.body.result.records[0]).to.deep.equal(record)
      expect(resp.body.success).to.eq(true)
    })
  })


  it('API: Aircan Submit', () => {
    resource_name = uuid();
    let body = {

      "package_id": "another-ds",
      "url": "https://gist.githubusercontent.com/hannelita/859e96ca8f60e7c973a2996ae9b6b307/raw/478c3c2f97ccf6d028181ae5dc0678a3783b09ca/r4.csv",
      "description": resource_name,
      "schema": {
        "fields": [{
            "name": "FID",
            "title": "FID",
            "type": "float",
            "description": "FID`"
          },
          {
            "name": "MktRF",
            "title": "MktRF",
            "type": "float",
            "description": "MktRF`"
          },
          {
            "name": "SMB",
            "title": "SMB",
            "type": "float",
            "description": "SMB`"
          },
          {
            "name": "HML",
            "title": "HML",
            "type": "float",
            "description": "HML`"
          },
          {
            "name": "RF",
            "title": "RF",
            "type": "float",
            "description": "RF`"
          }
        ]
      }
    }

    cy.request({
      method: 'POST',
      url: '/api/3/action/aircan_submit',
      headers: headers,
      body: body
    }).then((resp) => {
      resource_id = resp.body.result.id
      expect(resp.body.success).to.eq(true)
      let resource_url = `/dataset/another-ds/resource/${resource_id}`
      cy.wait(180000)
      cy.visit({
        url: resource_url
      }).then((resp) => {
        cy.get('.module-content > h2 ').contains('Data Dictionary')
      })
    })
  })

  it('API: Validate Data for Aircan Submit', () => {
    let resource_url = `/api/3/action/datastore_search?resource_id=${resource_id}`;
    let fields = [{
        "type": "int",
        "id": "_id"
      },
      {
        "type": "float8",
        "id": "FID"
      },
      {
        "type": "float8",
        "id": "MktRF"
      },
      {
        "type": "float8",
        "id": "SMB"
      },
      {
        "type": "float8",
        "id": "HML"
      },
      {
        "type": "float8",
        "id": "RF"
      },
      {
        "type": "float8",
        "id": "Mkt-RF"
      }
    ]
    let record = {
      "_id": 1,
      "FID": 192607,
      "MktRF": null,
      "SMB": -2.3,
      "HML": -2.87,
      "RF": 0.22,
      "Mkt-RF": 2.96
    }
    cy.request({
      url: resource_url,
      headers: headers
    }).then((resp) => {
      expect(resp.body.result.fields).to.deep.eq(fields)
      expect(resp.body.result.records_format).to.equal('objects')
      expect(resp.body.result.records[0]).to.deep.equal(record)
      expect(resp.body.success).to.eq(true)
    })
  })
})